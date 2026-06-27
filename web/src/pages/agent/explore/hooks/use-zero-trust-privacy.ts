import {
  useDeleteAgentSession,
  useFetchAgent,
} from '@/hooks/use-agent-request';
import { readPrivacyPolicy } from '@/pages/agent/utils/ephemeral-session';
import api from '@/utils/api';
import { get, post } from '@/utils/next-request';
import { useCallback, useEffect, useRef, useState } from 'react';
import { useParams } from 'react-router';
import { useExploreHardwareAuth } from '../hardware-auth-context';
import { useExploreUrlParams } from './use-explore-url-params';

type VaultStatus = {
  initialized?: boolean;
  needs_totp_setup?: boolean;
  vault_unlocked?: boolean;
  obsidian_unlocked?: boolean;
  master_configured?: boolean;
};

/**
 * Zero-trust privacy: purge ephemeral sessions on refresh, require HSM + vault unlock.
 */
export function useZeroTrustPrivacy(options?: {
  setDerivedMessages?: (messages: []) => void;
}) {
  const { id: canvasId } = useParams();
  const { sessionId, setSessionId } = useExploreUrlParams();
  const { data: canvasInfo } = useFetchAgent();
  const policy = readPrivacyPolicy(canvasInfo?.dsl);
  const { deleteAgentSession } = useDeleteAgentSession();
  const landedSessionIdRef = useRef(sessionId);
  const [vaultStatus, setVaultStatus] = useState<VaultStatus | null>(null);
  const [vaultBusy, setVaultBusy] = useState(false);
  const [vaultError, setVaultError] = useState<string | null>(null);
  const [setupBusy, setSetupBusy] = useState(false);
  const [setupError, setSetupError] = useState<string | null>(null);
  const [qrDataUrl, setQrDataUrl] = useState<string | null>(null);

  const hardware = useExploreHardwareAuth({
    required: policy.hardwareAuthRequired || policy.zeroTrust,
  });

  const refreshVaultStatus = useCallback(async () => {
    if (!policy.localVaultRequired) {
      setVaultStatus(null);
      return;
    }
    try {
      const res = await get(api.privacyVaultStatus);
      const payload = res?.data;
      if (payload?.code === 0) {
        setVaultStatus((payload.data as VaultStatus) ?? null);
      } else {
        setVaultStatus(null);
        setVaultError(payload?.message || 'Unable to read vault status.');
      }
    } catch {
      setVaultStatus(null);
      setVaultError('Unable to read vault status.');
    }
  }, [policy.localVaultRequired]);

  useEffect(() => {
    void refreshVaultStatus();
  }, [refreshVaultStatus, hardware.unlocked]);

  const beginTotpSetup = useCallback(async () => {
    setSetupBusy(true);
    setSetupError(null);
    try {
      const res = await post(api.privacyVaultSetup, {});
      const payload = res?.data;
      if (payload?.code !== 0) {
        setSetupError(payload?.message || 'Vault enrollment failed.');
        return;
      }
      const data = payload.data as { qr_data_url?: string };
      setQrDataUrl(data?.qr_data_url ?? null);
      await refreshVaultStatus();
    } catch (error) {
      setSetupError(
        error instanceof Error ? error.message : 'Vault enrollment failed.',
      );
    } finally {
      setSetupBusy(false);
    }
  }, [refreshVaultStatus]);

  const unlockVault = useCallback(
    async (totpCode: string) => {
      setVaultBusy(true);
      setVaultError(null);
      try {
        const res = await post(api.privacyVaultUnlock, {
          totp_code: totpCode,
          unlock_vault: true,
          unlock_obsidian: policy.obsidian2fa,
          agent_id: canvasId,
        });
        const payload = res?.data;
        if (payload?.code !== 0) {
          setVaultError(payload?.message || 'Vault unlock failed.');
          return false;
        }
        await refreshVaultStatus();
        return true;
      } catch (error) {
        setVaultError(
          error instanceof Error ? error.message : 'Vault unlock failed.',
        );
        return false;
      } finally {
        setVaultBusy(false);
      }
    },
    [canvasId, policy.obsidian2fa, refreshVaultStatus],
  );

  const purgeSession = useCallback(
    async (targetSessionId: string) => {
      if (!policy.ephemeralSessions || !canvasId || !targetSessionId) {
        return;
      }
      try {
        await deleteAgentSession({ canvasId, sessionId: targetSessionId });
      } catch (error) {
        console.warn('Failed to purge ephemeral agent session', error);
      }
      options?.setDerivedMessages?.([]);
      setSessionId('', true);
    },
    [
      canvasId,
      deleteAgentSession,
      options,
      policy.ephemeralSessions,
      setSessionId,
    ],
  );

  useEffect(() => {
    const landedWithSession = landedSessionIdRef.current;
    if (policy.ephemeralSessions && canvasId && landedWithSession) {
      void purgeSession(landedWithSession);
    }
  }, [canvasId, policy.ephemeralSessions, purgeSession]);

  const needsTotpSetup =
    policy.localVaultRequired &&
    vaultStatus !== null &&
    Boolean(vaultStatus.needs_totp_setup ?? !vaultStatus.initialized);
  const vaultLocked =
    policy.localVaultRequired &&
    vaultStatus !== null &&
    Boolean(vaultStatus.initialized) &&
    !vaultStatus?.vault_unlocked;
  const obsidianLocked =
    policy.obsidian2fa &&
    vaultStatus !== null &&
    Boolean(vaultStatus.initialized) &&
    !vaultStatus?.obsidian_unlocked;

  const canUseAgent = !hardware.locked && !vaultLocked && !needsTotpSetup;

  return {
    policy,
    ephemeral: policy.ephemeralSessions,
    hardwareAuthRequired: policy.hardwareAuthRequired,
    needsHsmEnrollment: hardware.needsRegistration,
    vaultLocked,
    needsTotpSetup,
    obsidianLocked,
    vaultBusy,
    vaultError,
    setupBusy,
    setupError,
    qrDataUrl,
    beginTotpSetup,
    unlockVault,
    refreshVaultStatus,
    canUseAgent,
    purgeSession,
    hardware,
  };
}

/** @deprecated use useZeroTrustPrivacy */
export const useEphemeralSessionPrivacy = useZeroTrustPrivacy;
