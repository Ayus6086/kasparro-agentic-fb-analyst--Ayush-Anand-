from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, List, Any

import logging
import math
import json
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class DataSchema:
    """
    Explicit schema definition for the ads dataset.
    We only enforce *category* of type (string vs numeric), not exact dtypes.
    """
    required_columns: List[str]
    string_columns: List[str]
    numeric_columns: List[str]


DEFAULT_SCHEMA = DataSchema(
    required_columns=[
        "campaign_name",
        "date",
        "spend",
        "impressions",
        "clicks",
        "purchases",
        "revenue",
        "creative_message",
    ],
    string_columns=[
        "campaign_name",
        "creative_message",
        "adset_name",
        "creative_type",
        "audience_type",
    ],
    numeric_columns=[
        "spend",
        "impressions",
        "clicks",
        "ctr",
        "purchases",
        "revenue",
        "roas",
    ],
)


class DataAgent:
    """
    Responsible for:
    - Loading the CSV
    - Validating schema
    - Computing metrics (CTR/ROAS if missing/broken)
    - Producing summaries and time-series aggregates
    """

    def __init__(self, sample_frac: float = 0.2, schema: DataSchema = DEFAULT_SCHEMA):
        self.sample_frac = sample_frac
        self.schema = schema


    @staticmethod
    def _save_error_log(path: Path, payload: Dict[str, Any]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2)


    def _validate_schema(self, df: pd.DataFrame, log_dir: Path = Path("logs")) -> None:
        """
        Validate that the dataframe roughly conforms to the expected schema.

        - Fails on:
          * missing required columns
          * empty dataframe
          * obvious type mismatches for key numeric/string fields

        - Does NOT fail on:
          * extra/unexpected columns (we just log them as a warning)
        """
        errors: Dict[str, Any] = {}

        cols = set(df.columns)
        required = set(self.schema.required_columns)

        missing = sorted(list(required - cols))
        unexpected = sorted(list(cols - required))

        if missing:
            errors["missing_columns"] = missing

        if unexpected:
            logger.warning(
                "Unexpected columns present (allowed, will be ignored in schema check): %s",
                sorted(unexpected),
            )

        if df.empty:
            errors["empty_dataframe"] = True

        type_issues: Dict[str, str] = {}

        for col in self.schema.numeric_columns:
            if col in df.columns:
                if not pd.api.types.is_numeric_dtype(df[col].dtype):
                    type_issues[col] = f"expected numeric, got {df[col].dtype}"

        for col in self.schema.string_columns:
            if col in df.columns:
                if not pd.api.types.is_string_dtype(df[col].dtype):
                    if pd.api.types.is_numeric_dtype(df[col].dtype):
                        type_issues[col] = f"expected string-like, got {df[col].dtype}"

        if type_issues:
            errors["type_mismatches"] = type_issues

        if errors:
            error_payload = {
                "error": "Schema validation failed",
                "details": errors,
            }
            log_path = log_dir / "schema_error.json"
            self._save_error_log(log_path, error_payload)
            logger.error("Schema validation failed. Details written to %s", log_path)

            base_msg = "Schema validation failed."
            if "missing_columns" in errors:
                base_msg += f" Missing required columns: {errors['missing_columns']}."

            raise ValueError(
                base_msg + " See logs/schema_error.json for details."
            )

        logger.info("Schema validation passed with required columns present: %s", sorted(required))


    def load(self, path: Path, log_dir: Path = Path("logs")) -> pd.DataFrame:
        """
        Load CSV from disk with robust error handling and schema validation.
        """
        try:
            if not path.exists():
                payload = {
                    "error": "File not found",
                    "path": str(path),
                }
                self._save_error_log(log_dir / "data_load_error.json", payload)
                logger.error("Data file not found at %s", path)
                raise FileNotFoundError(f"Data file not found at {path}")

            df = pd.read_csv(path)

            if "date" in df.columns:
                df["date"] = pd.to_datetime(df["date"], errors="coerce")

            self._validate_schema(df, log_dir=log_dir)

            if 0 < self.sample_frac < 1.0:
                df = df.sample(frac=self.sample_frac, random_state=42).reset_index(drop=True)

            return df

        except pd.errors.EmptyDataError:
            payload = {
                "error": "Empty CSV file",
                "path": str(path),
            }
            self._save_error_log(log_dir / "data_load_error.json", payload)
            logger.exception("Empty CSV file at %s", path)
            raise ValueError("Input data file is empty. Please provide a non-empty CSV.")

        except pd.errors.ParserError as e:
            payload = {
                "error": "CSV parse error",
                "path": str(path),
                "message": str(e),
            }
            self._save_error_log(log_dir / "data_load_error.json", payload)
            logger.exception("CSV parse error at %s", path)
            raise ValueError("Failed to parse CSV. Please check file formatting.")

    def add_metrics(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Ensure ctr and roas are present and consistent.
        Handle NaNs, infinities and divide-by-zero gracefully.
        """
        df = df.copy()

        for col in self.schema.numeric_columns:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors="coerce")

        if "ctr" in df.columns:
            df["ctr"] = df["ctr"].astype(float)
        if "clicks" in df.columns and "impressions" in df.columns:
            computed_ctr = df["clicks"] / df["impressions"].replace({0: pd.NA})
            df["ctr"] = df["ctr"].fillna(computed_ctr)

        if "roas" in df.columns:
            df["roas"] = df["roas"].astype(float)
        if "revenue" in df.columns and "spend" in df.columns:
            computed_roas = df["revenue"] / df["spend"].replace({0: pd.NA})
            df["roas"] = df["roas"].fillna(computed_roas)

        for col in self.schema.numeric_columns:
            if col in df.columns:
                df[col] = df[col].replace([math.inf, -math.inf], pd.NA)
                df[col] = df[col].fillna(0.0)

        if "spend" in df.columns:
            df["anomaly_negative_spend"] = df["spend"] < 0

        return df

    def summarize(self, df: pd.DataFrame) -> Dict[str, Any]:
        date_min = df["date"].min()
        date_max = df["date"].max()
        total_spend = float(df["spend"].sum())
        avg_ctr = float(df["ctr"].mean())
        avg_roas = float(df["roas"].mean())

        camp_roas = df.groupby("campaign_name")["roas"].mean().sort_values(ascending=False)
        top_by_roas = camp_roas.to_dict()

        summary = {
            "date_range": [str(date_min.date()), str(date_max.date())],
            "total_spend": total_spend,
            "avg_ctr": avg_ctr,
            "avg_roas": avg_roas,
            "campaigns_count": int(df["campaign_name"].nunique()),
            "top_by_roas": top_by_roas,
        }

        self._save_error_log(Path("logs") / "data_summary.json", summary)
        logger.info("Data summary written to logs/data_summary.json")

        return summary

    def detect_schema_drift(self, df):
        """
        Lightweight schema drift detector:
        - compares current columns to the expected schema
        - returns dict with 'added' and 'removed' columns
        """
        current_cols = set(df.columns)
        expected = set(self.schema.required_columns)

        added = sorted(list(current_cols - expected))
        removed = sorted(list(expected - current_cols))

        drift = {
            "added_columns": added,
            "removed_columns": removed
        }

        if added or removed:
            log_dir = Path("logs")
            log_dir.mkdir(parents=True, exist_ok=True)

            with open(log_dir / "schema_drift.json", "w", encoding="utf-8") as f:
                json.dump(drift, f, indent=2)

        return drift

    def aggregate_timeseries(self, df: pd.DataFrame) -> Dict[str, List[Dict[str, Any]]]:
        """
        Returns a mapping: campaign_name -> list of daily dicts (sorted by date).
        Each dict contains metrics for that date.
        """
        out: Dict[str, List[Dict[str, Any]]] = {}
        if "date" not in df.columns:
            return out

        df_sorted = df.sort_values(["campaign_name", "date"])
        for camp, grp in df_sorted.groupby("campaign_name"):
            series = []
            for _, row in grp.iterrows():
                series.append(
                    {
                        "date": row["date"],
                        "spend": float(row.get("spend", 0.0)),
                        "impressions": float(row.get("impressions", 0.0)),
                        "clicks": float(row.get("clicks", 0.0)),
                        "ctr": float(row.get("ctr", 0.0)),
                        "revenue": float(row.get("revenue", 0.0)),
                        "roas": float(row.get("roas", 0.0)),
                        "purchases": float(row.get("purchases", 0.0)),
                    }
                )
            out[camp] = series
        return out
