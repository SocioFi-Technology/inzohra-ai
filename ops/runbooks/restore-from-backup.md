# Restore from backup

## Postgres PITR

Point-in-time recovery window: 30 days.

1. Pick the target recovery time.
2. Spin up a scratch Postgres instance with the latest base backup.
3. Replay WAL up to the target time.
4. Dump and reload only the required tables / rows into the restore target.

Never roll back the production primary in-place. Always restore to a scratch and compare.

## S3

Versioning is on. Every object has historical versions for 90 days before lifecycling to Glacier.

To restore an object:
`aws s3api get-object --bucket <bucket> --key <key> --version-id <id> <dest>`

## Drill

Quarterly. Restore a random project from 7-day-old backup to the scratch env, run `pnpm test:fixture` against it, confirm green. Document the drill in `ops/drill-log.md`.
