export const ACTIVE_JOB_ID_KEY = "video_auto_cut_active_job_id";

const PENDING_INVITE_CODE_KEY_PREFIX = "video_auto_cut_pending_invite_code";
export const LEGACY_PENDING_INVITE_CODE_KEY = PENDING_INVITE_CODE_KEY_PREFIX;

export function pendingInviteCodeKeyForUser(userId: string): string {
  return `${PENDING_INVITE_CODE_KEY_PREFIX}:${userId}`;
}
