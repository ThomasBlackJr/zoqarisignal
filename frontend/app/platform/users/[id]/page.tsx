import { PlatformUser } from "@/components/platform-user";
export default async function Page({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  return <PlatformUser id={(await params).id} />;
}
