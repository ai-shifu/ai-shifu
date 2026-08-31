import { ReferralInviteLanding } from '../ReferralInviteLanding';

type InviteCodePageProps = {
  params: Promise<{
    inviteCode?: string;
  }>;
};

export default async function InviteCodePage({ params }: InviteCodePageProps) {
  const { inviteCode = '' } = await params;
  return <ReferralInviteLanding initialInviteCode={inviteCode} />;
}
