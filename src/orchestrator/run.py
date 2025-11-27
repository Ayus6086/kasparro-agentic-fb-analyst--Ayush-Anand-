# src/orchestrator/run.py
import json, os
from pathlib import Path
from configparser import ConfigParser
import yaml

# local imports
from src.agents.data_agent import DataAgent
from src.agents.planner_agent import PlannerAgent
from src.agents.insight_agent import InsightAgent
from src.agents.evaluator_agent import EvaluatorAgent
from src.agents.creative_agent import CreativeAgent

CONFIG_PATH = Path("config/config.yaml")
DATA_PATH = Path("data/sample.csv")
OUT_DIR = Path("reports")
LOG_DIR = Path("logs")

def load_config(path=CONFIG_PATH):
    with open(path, 'r') as f:
        return yaml.safe_load(f)

def main(task_text="Analyze ROAS drop"):
    cfg = load_config()
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)

    data_agent = DataAgent(sample_frac=cfg.get('sample_frac', 0.2))
    df = data_agent.load(DATA_PATH)
    df = data_agent.add_metrics(df)
    summary = data_agent.summarize(df)

    planner = PlannerAgent(roas_drop_pct=cfg.get('roas_drop_pct',20))
    plan = planner.decompose(task_text, summary, df)

    all_insights = {}
    all_creatives = {}

    insight_agent = InsightAgent()
    evaluator = EvaluatorAgent()
    creative_agent = CreativeAgent()

    for camp in plan['target_campaigns']:
        ts_map = data_agent.aggregate_timeseries(df[df['campaign_name']==camp])
        timeseries = ts_map.get(camp, [])
        hypos = insight_agent.generate_hypotheses(camp, timeseries)
        # Evaluate hypotheses
        for h in hypos:
            if h.get('id') == 'h_ctr_drop':
                half = len(timeseries)//2
                pre = [d['ctr'] for d in timeseries[:half]]
                post = [d['ctr'] for d in timeseries[half:]]
                evidence = evaluator.validate_ctr_change(pre, post)
                h['evidence'] = evidence
        all_insights[camp] = hypos

        # Generate creatives if CTR low
        df_camp = df[df['campaign_name']==camp]
        top_examples = df_camp['creative_message'].fillna("Our product").tolist()[:5]
        creatives = creative_agent.suggest(camp, top_examples)
        all_creatives[camp] = creatives

    # Save outputs
    with open(OUT_DIR / "insights.json", "w") as f:
        json.dump(all_insights, f, indent=2)
    with open(OUT_DIR / "creatives.json", "w") as f:
        json.dump(all_creatives, f, indent=2)
    with open(OUT_DIR / "report.md", "w") as f:
        f.write(f"# Analysis report\n\nTask: {task_text}\n\nSummary: {summary}\n\nCampaigns analyzed: {plan['target_campaigns']}\n")

    print("Done. Reports written to 'reports/'")

if __name__ == "__main__":
    main()
