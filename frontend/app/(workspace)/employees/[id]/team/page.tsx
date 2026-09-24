import { ManagerTeams } from "@/components/manager-teams";
export default async function Page({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  return <ManagerTeams id={id} />;
}
