import { describe, expect, it } from "vitest";

import {
  canManageDepartment,
  displayName,
  isSuperAdmin,
  primaryMembership,
  roleLabel,
} from "@/features/auth/guards";
import type { Membership, User } from "@/types/auth";

const membership: Membership = {
  department_id: "1d2c3b4a-5e6f-4a7b-8c9d-0e1f2a3b4c5d",
  department_code: "QA-LAB",
  department_name: "Quality Lab",
  role: "department_admin",
};

const user: User = {
  id: "6f1e6a2c-5f8a-4f3d-9d1e-2b3c4d5e6f70",
  email: "officer@example.test",
  full_name: "A. Officer",
  is_super_admin: false,
  memberships: [membership],
};

describe("auth guards", () => {
  it("returns the first membership as the default context", () => {
    expect(primaryMembership(user)?.department_code).toBe("QA-LAB");
    expect(primaryMembership(null)).toBeNull();
  });

  it("detects super admins", () => {
    expect(isSuperAdmin(user)).toBe(false);
    expect(isSuperAdmin({ ...user, is_super_admin: true })).toBe(true);
    expect(isSuperAdmin(null)).toBe(false);
  });

  it("allows management only in an administered department", () => {
    expect(canManageDepartment(user, membership.department_id)).toBe(true);
    expect(canManageDepartment(user, "00000000-0000-4000-8000-000000000000")).toBe(false);
    expect(canManageDepartment(null, membership.department_id)).toBe(false);
  });

  it("lets a super admin manage any department", () => {
    expect(
      canManageDepartment(
        { ...user, is_super_admin: true },
        "00000000-0000-4000-8000-000000000000",
      ),
    ).toBe(true);
  });

  it("labels roles and falls back to email for display", () => {
    expect(roleLabel(membership)).toBe("Department admin");
    expect(displayName(user)).toBe("A. Officer");
    expect(displayName({ ...user, full_name: null })).toBe("officer@example.test");
  });
});
