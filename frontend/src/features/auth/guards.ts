import type { Membership, User } from "@/types/auth";

/** One department is the default context; the backend still authorizes every request. */
export function primaryMembership(user: User | null): Membership | null {
  return user?.memberships[0] ?? null;
}

export function isSuperAdmin(user: User | null): boolean {
  return user?.is_super_admin ?? false;
}

export function canManageDepartment(user: User | null, departmentId: string): boolean {
  if (!user) {
    return false;
  }
  if (user.is_super_admin) {
    return true;
  }
  return user.memberships.some(
    (membership) =>
      membership.department_id === departmentId && membership.role === "department_admin",
  );
}

export function roleLabel(membership: Membership): string {
  return membership.role === "department_admin" ? "Department admin" : "Department user";
}

export function displayName(user: User | null): string {
  if (!user) {
    return "";
  }
  return user.full_name?.trim() || user.email;
}
