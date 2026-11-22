import { z } from "zod";

export const membershipRoleSchema = z.enum(["department_admin", "department_user"]);

export const membershipSchema = z.object({
  department_id: z.string().uuid(),
  department_code: z.string(),
  department_name: z.string(),
  role: membershipRoleSchema,
});

export const userSchema = z.object({
  id: z.string().uuid(),
  email: z.string(),
  full_name: z.string().nullable(),
  is_super_admin: z.boolean(),
  memberships: z.array(membershipSchema),
});

export const tokenResponseSchema = z.object({
  access_token: z.string(),
  token_type: z.literal("bearer"),
  expires_in: z.number(),
  user: userSchema,
});

export const meResponseSchema = z.object({ user: userSchema });

export type Membership = z.infer<typeof membershipSchema>;
export type MembershipRole = z.infer<typeof membershipRoleSchema>;
export type User = z.infer<typeof userSchema>;
export type TokenResponse = z.infer<typeof tokenResponseSchema>;
