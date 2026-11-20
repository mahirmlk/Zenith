import InvitationAcceptance from './page.client';

interface PageProps {
  searchParams: Promise<{ invitation_id?: string | string[]; token_hash?: string | string[]; type?: string | string[]; code?: string | string[] }>;
}

export default async function AcceptProjectInvitationPage({ searchParams }: PageProps) {
  const params = await searchParams;
  const invitationId = Array.isArray(params.invitation_id) ? params.invitation_id[0] : params.invitation_id;
  const tokenHash = Array.isArray(params.token_hash) ? params.token_hash[0] : params.token_hash;
  const authType = Array.isArray(params.type) ? params.type[0] : params.type;
  const code = Array.isArray(params.code) ? params.code[0] : params.code;
  return <InvitationAcceptance invitationId={invitationId ?? ''} tokenHash={tokenHash} authType={authType} code={code} />;
}
