/**
 * Server-side Postgres pool for Next.js API routes.
 * Uses the `pg` package (already in dependencies).
 */
import { Pool } from "pg";

declare global {
  // Preserve the pool across hot-reloads in dev.
  // eslint-disable-next-line no-var
  var __pgPool: Pool | undefined;
}

function createPool(): Pool {
  return new Pool({
    connectionString: process.env.DATABASE_URL!,
    max: 5,
    idleTimeoutMillis: 30_000,
    connectionTimeoutMillis: 5_000,
  });
}

export const pool: Pool = globalThis.__pgPool ?? (globalThis.__pgPool = createPool());

/** Run a parameterised query and return all rows. */
export async function query<T = Record<string, unknown>>(
  sql: string,
  params?: unknown[]
): Promise<T[]> {
  const result = await pool.query(sql, params);
  return result.rows as T[];
}

/** Run a query and return the first row (or null). */
export async function queryOne<T = Record<string, unknown>>(
  sql: string,
  params?: unknown[]
): Promise<T | null> {
  const rows = await query<T>(sql, params);
  return rows[0] ?? null;
}
