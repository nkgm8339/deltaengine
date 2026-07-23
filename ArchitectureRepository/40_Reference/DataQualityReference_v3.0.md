# DataQualityReference_v3.0

# Purpose

Defines the canonical data quality terminology, validation principles, and measurement metrics used throughout the Order Flow Analysis Platform.

------------------------------------------------------------------------

## Quality Concepts

| Term | Definition |
|------|-----------|
| Completeness | Required data fields are present and non-null |
| Accuracy | Values correctly represent the original market data |
| Consistency | Identical rules are applied across all datasets |
| Timeliness | Data is available within required processing windows |
| Validity | Data conforms to defined schemas and constraints |
| Uniqueness | Duplicate records are prevented or identified |
| Traceability | Data lineage can be tracked from source to output |

------------------------------------------------------------------------

## Quality Metrics

| Metric | Definition |
|--------|-----------|
| Completeness Rate | Ratio of available required fields compared with expected fields |
| Accuracy Rate | Ratio of correctly represented values compared with validated values |
| Consistency Rate | Measurement of agreement between related datasets or rules |
| Validity Rate | Ratio of records conforming to defined formats and constraints |
| Duplicate Rate | Measurement of duplicate records detected within a dataset |
| Timeliness Metric | Measurement of data availability within required time constraints |
| Error Rate | Ratio of invalid or failed records compared with total processed records |

------------------------------------------------------------------------

## Reference Rules

-   This document is the SSOT for data quality terminology and metrics.
-   Validation modules shall reference these definitions.
-   Implementation-specific validation rules shall extend but not
    redefine these concepts.

Status: Phase4 Reference Enhancement
