import { z } from "zod";

/**
 * Response contracts mirror docs/api/API_CONTRACT.md. Only shapes used by implemented
 * screens are validated here; the rest are added with their features.
 */
export const healthSchema = z.object({
  status: z.literal("ok"),
  service: z.string(),
  version: z.string().nullable().optional(),
  environment: z.string().nullable().optional(),
});

export type Health = z.infer<typeof healthSchema>;

export const readinessSchema = z.object({
  status: z.literal("ready"),
  database: z.literal("ok"),
});

export type Readiness = z.infer<typeof readinessSchema>;
