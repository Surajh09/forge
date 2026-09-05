import { OrganizationList } from "@clerk/nextjs";

export default function SelectOrgPage() {
  return (
    <main className="flex min-h-[80vh] flex-col items-center justify-center gap-6 p-6">
      <div className="text-center">
        <h1 className="text-2xl font-semibold tracking-tight">Choose an organization</h1>
        <p className="text-muted-foreground mt-1 text-sm">
          Forge is organization-scoped. Features, sessions and context never cross tenants.
        </p>
      </div>
      <OrganizationList
        hidePersonal
        afterSelectOrganizationUrl="/dashboard"
        afterCreateOrganizationUrl="/dashboard"
      />
    </main>
  );
}
