import { auth } from "@clerk/nextjs/server";
import { Trash2, UserMinus } from "lucide-react";

import { RoleBadge } from "@/components/badges";
import { AdminActions } from "@/components/forms/admin-actions";
import { ConfirmButton } from "@/components/forms/confirm-button";
import { CreateTeamForm } from "@/components/forms/create-team-form";
import { nativeSelectClass } from "@/components/forms/field";
import { SurfaceFrame } from "@/components/ui/surface";
import { EmptyState, PageHeader, SectionHeader } from "@/components/page-header";
import { SubmitButton } from "@/components/submit-button";
import { Badge } from "@/components/ui/badge";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { addTeamMemberAction, deleteTeamAction, removeTeamMemberAction } from "@/lib/actions";
import { get } from "@/lib/api";
import type { Team, User } from "@/lib/types";

export default async function AdminPage() {
  const { has } = await auth();
  if (!has({ role: "org:admin" })) {
    return (
      <EmptyState
        title="Admins only"
        body="Your Clerk organization role is not admin. Ask an organization admin to change it in Clerk."
      />
    );
  }

  const [teams, users] = await Promise.all([get<Team[]>("/teams"), get<User[]>("/users")]);

  return (
    <>
      <PageHeader
        title="Administration"
        description="Teams and membership live in Forge; identity, organization membership and roles come from Clerk."
      />

      <section className="mb-10">
        <AdminActions />
      </section>

      <section className="mb-10">
        <SectionHeader title="Teams" description="Attached to features; membership grants access and teammate session visibility." />
        <Card className="mb-4">
          <CardHeader>
            <CardTitle>New team</CardTitle>
            <CardDescription>Teams are attached to features; membership grants access to those features and visibility of teammates&apos; sessions.</CardDescription>
          </CardHeader>
          <CardContent>
            <CreateTeamForm />
          </CardContent>
        </Card>

        {teams.length === 0 ? (
          <EmptyState title="No teams yet" body="Create one above, or load the demo data." />
        ) : (
          <div className="grid gap-4 md:grid-cols-2">
            {teams.map((team) => {
              const memberIds = new Set(team.members.map((m) => m.id));
              const candidates = users.filter((u) => !memberIds.has(u.id));
              return (
                <Card key={team.id}>
                  <CardHeader>
                    <CardTitle className="flex items-center justify-between gap-2">
                      {team.name}
                      <ConfirmButton
                        action={deleteTeamAction.bind(null, team.id)}
                        confirm={`Delete team "${team.name}"? Members lose access granted through it.`}
                        variant="ghost"
                        size="icon-sm"
                        aria-label="Delete team"
                      >
                        <Trash2 />
                      </ConfirmButton>
                    </CardTitle>
                    {team.description && <CardDescription>{team.description}</CardDescription>}
                  </CardHeader>
                  <CardContent className="grid gap-3">
                    <ul className="grid gap-1.5 text-sm">
                      {team.members.length === 0 && <li className="text-muted-foreground">No members.</li>}
                      {team.members.map((m) => (
                        <li key={m.id} className="flex items-center justify-between gap-2">
                          <span>
                            {m.display_name}
                            {m.is_demo && <Badge variant="outline" className="ml-2">demo</Badge>}
                          </span>
                          <ConfirmButton
                            action={removeTeamMemberAction.bind(null, team.id, m.id)}
                            variant="ghost"
                            size="icon-xs"
                            aria-label={`Remove ${m.display_name}`}
                          >
                            <UserMinus />
                          </ConfirmButton>
                        </li>
                      ))}
                    </ul>
                    {candidates.length > 0 && (
                      <form action={addTeamMemberAction.bind(null, team.id)} className="flex items-center gap-2">
                        <select name="user_id" className={nativeSelectClass} defaultValue="" required aria-label="Add member">
                          <option value="" disabled>
                            Add a member…
                          </option>
                          {candidates.map((u) => (
                            <option key={u.id} value={u.id}>
                              {u.display_name}
                            </option>
                          ))}
                        </select>
                        <SubmitButton variant="outline" size="sm" pendingLabel="Adding…">
                          Add
                        </SubmitButton>
                      </form>
                    )}
                  </CardContent>
                </Card>
              );
            })}
          </div>
        )}
      </section>

      <section>
        <SectionHeader title="People" description="Identity comes from Clerk; Forge stores a per-organization snapshot." />
        <SurfaceFrame>
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead>Name</TableHead>
                <TableHead>Email</TableHead>
                <TableHead>Role</TableHead>
                <TableHead>Source</TableHead>
                <TableHead>Clerk user id</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {users.map((u) => (
                <TableRow key={u.id}>
                  <TableCell className="font-medium">{u.display_name}</TableCell>
                  <TableCell className="text-muted-foreground">{u.email ?? "—"}</TableCell>
                  <TableCell>
                    <RoleBadge role={u.role} />
                  </TableCell>
                  <TableCell>{u.is_demo ? <Badge variant="outline">demo</Badge> : <Badge variant="secondary">Clerk</Badge>}</TableCell>
                  <TableCell className="text-muted-foreground font-mono text-xs">{u.id}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </SurfaceFrame>
      </section>
    </>
  );
}
