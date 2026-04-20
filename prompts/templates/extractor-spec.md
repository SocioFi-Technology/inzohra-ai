# Extractor spec template

## Name

`<SnakeCaseAgent>`

## Version

`1.0.0`

## Input

Document type + page region definition.

## Output

Pydantic / Zod schema URI.

## Dual-track

Text track: ...
Vision track: ...
Merge policy: ...

## Confidence

Per-field confidence rules.

## Bbox

Every emitted field carries a bbox. No exceptions.

## Fixture test

Positive + negative golden JSON.

## Implementation

`services/ingestion/app/extractors/<name>.py`.
