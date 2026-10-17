import { PlatformOrganization } from "@/components/platform";
export default async function Page({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  return <PlatformOrganization id={(await params).id} />;
}
