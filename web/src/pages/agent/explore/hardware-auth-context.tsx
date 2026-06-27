import api from '@/utils/api';
import {
  clearHardwareAuthToken,
  getHardwareAuthToken,
  setHardwareAuthToken,
} from '@/utils/hardware-auth-token';
import { get, post } from '@/utils/next-request';
import type {
  PublicKeyCredentialCreationOptionsJSON,
  PublicKeyCredentialRequestOptionsJSON,
} from '@simplewebauthn/browser';
import {
  startAuthentication,
  startRegistration,
} from '@simplewebauthn/browser';
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';

/** Cross-platform physical module only — not platform authenticators. */
const USE_SECURITY_KEY = true;

const HSM_ERRORS = {
  statusFailed: 'Unable to verify module enrollment status.',
  provisionStart: 'Unable to start HSM provisioning.',
  provisionFailed: 'HSM enrollment did not complete.',
  verifyStart: 'Unable to initiate module verification.',
  verifyFailed: 'Module verification failed.',
  tokenMissing: 'Hardware token unavailable.',
} as const;

/** Map backend/API messages to obfuscated user-facing copy. */
function toUserFacingError(
  message: string | undefined,
  fallback: string,
): string {
  if (!message) {
    return fallback;
  }
  const lower = message.toLowerCase();
  if (
    lower.includes('yubikey') ||
    lower.includes('fido') ||
    lower.includes('webauthn') ||
    lower.includes('security key') ||
    lower.includes('passkey') ||
    lower.includes('touch id') ||
    (lower.includes('credential') && lower.includes('required')) ||
    lower.includes('enrollment payload') ||
    lower.includes('verification payload') ||
    lower.includes('has no attribute') ||
    lower.includes('attributeerror') ||
    lower.includes('hardware module operation failed')
  ) {
    if (lower.includes('expired') || lower.includes('challenge')) {
      return 'Module session expired. Reconnect your physical module and try again.';
    }
    if (
      lower.includes('register') ||
      lower.includes('enroll') ||
      lower.includes('no ') ||
      lower.includes('unknown')
    ) {
      return 'No hardware module enrolled. Complete initial HSM provisioning first.';
    }
    return fallback;
  }
  return message;
}

type HardwareAuthContextValue = {
  registered: boolean | null;
  needsRegistration: boolean;
  needsReprovision: boolean;
  unlocked: boolean;
  locked: boolean;
  busy: boolean;
  error: string | null;
  registerKey: () => Promise<boolean>;
  unlock: () => Promise<boolean>;
  refreshStatus: () => Promise<void>;
};

const HardwareAuthContext = createContext<HardwareAuthContextValue | null>(
  null,
);

type HardwareAuthProviderProps = {
  children: ReactNode;
};

/**
 * In-memory HSM session scoped to the explore layout.
 * Survives new chats, sends, and USB unplug; cleared only on full page reload.
 */
export function HardwareAuthProvider({ children }: HardwareAuthProviderProps) {
  const [registered, setRegistered] = useState<boolean | null>(null);
  const [needsReprovision, setNeedsReprovision] = useState(false);
  const [unlocked, setUnlocked] = useState(() =>
    Boolean(getHardwareAuthToken()),
  );
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const refreshStatus = useCallback(async () => {
    try {
      const { data } = await get(api.privacyStatus);
      if (data?.code === 0) {
        const corrupted = Boolean(
          data.data?.store_corrupted || data.data?.needs_reprovision,
        );
        setNeedsReprovision(corrupted);
        setRegistered(corrupted ? false : Boolean(data.data?.registered));
      }
    } catch {
      setRegistered(false);
      setNeedsReprovision(false);
    }
  }, []);

  useEffect(() => {
    void refreshStatus();
  }, [refreshStatus]);

  const performUnlock = useCallback(async (): Promise<boolean> => {
    const optRes = await post(api.webauthnAuthenticateOptions, {});
    if (optRes?.data?.code !== 0) {
      throw new Error(
        toUserFacingError(optRes?.data?.message, HSM_ERRORS.verifyStart),
      );
    }
    const assertion = await startAuthentication({
      optionsJSON: optRes.data.data as PublicKeyCredentialRequestOptionsJSON,
      useSecurityKey: USE_SECURITY_KEY,
    });
    const verifyRes = await post(api.webauthnAuthenticateVerify, {
      credential: assertion,
    });
    if (verifyRes?.data?.code !== 0) {
      throw new Error(
        toUserFacingError(verifyRes?.data?.message, HSM_ERRORS.verifyFailed),
      );
    }
    const token = verifyRes.data?.data?.hardware_token as string;
    if (!token) {
      throw new Error(HSM_ERRORS.tokenMissing);
    }
    setHardwareAuthToken(token);
    setUnlocked(true);
    return true;
  }, []);

  const unlock = useCallback(async (): Promise<boolean> => {
    setBusy(true);
    setError(null);
    try {
      return await performUnlock();
    } catch (err) {
      clearHardwareAuthToken();
      setUnlocked(false);
      setError(
        err instanceof Error
          ? toUserFacingError(err.message, HSM_ERRORS.verifyFailed)
          : HSM_ERRORS.verifyFailed,
      );
      return false;
    } finally {
      setBusy(false);
    }
  }, [performUnlock]);

  const registerKey = useCallback(async (): Promise<boolean> => {
    setBusy(true);
    setError(null);
    let enrolled = false;
    try {
      const optRes = await post(api.webauthnRegisterOptions, {});
      if (optRes?.data?.code !== 0) {
        throw new Error(
          toUserFacingError(optRes?.data?.message, HSM_ERRORS.provisionStart),
        );
      }
      const attestation = await startRegistration({
        optionsJSON: optRes.data.data as PublicKeyCredentialCreationOptionsJSON,
        useSecurityKey: USE_SECURITY_KEY,
      });
      const verifyRes = await post(api.webauthnRegisterVerify, {
        credential: attestation,
      });
      if (verifyRes?.data?.code !== 0) {
        throw new Error(
          toUserFacingError(
            verifyRes?.data?.message,
            HSM_ERRORS.provisionFailed,
          ),
        );
      }
      enrolled = true;
      setRegistered(true);
      setNeedsReprovision(false);
      return await performUnlock();
    } catch (err) {
      clearHardwareAuthToken();
      setUnlocked(false);
      const fallback = enrolled
        ? HSM_ERRORS.verifyFailed
        : HSM_ERRORS.provisionFailed;
      setError(
        err instanceof Error
          ? toUserFacingError(err.message, fallback)
          : fallback,
      );
      return false;
    } finally {
      setBusy(false);
    }
  }, [performUnlock]);

  const value = useMemo<HardwareAuthContextValue>(
    () => ({
      registered,
      needsRegistration: registered === false,
      needsReprovision,
      unlocked,
      locked: false,
      busy,
      error,
      registerKey,
      unlock,
      refreshStatus,
    }),
    [
      registered,
      needsReprovision,
      unlocked,
      busy,
      error,
      registerKey,
      unlock,
      refreshStatus,
    ],
  );

  return (
    <HardwareAuthContext.Provider value={value}>
      {children}
    </HardwareAuthContext.Provider>
  );
}

export function useExploreHardwareAuth(options?: { required?: boolean }) {
  const ctx = useContext(HardwareAuthContext);
  if (!ctx) {
    throw new Error(
      'useExploreHardwareAuth must be used within HardwareAuthProvider',
    );
  }
  const required = options?.required ?? false;
  return useMemo(
    () => ({
      ...ctx,
      locked: required && !ctx.unlocked,
    }),
    [ctx, required],
  );
}
