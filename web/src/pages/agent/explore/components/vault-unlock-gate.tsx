import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { KeyRound, Lock } from 'lucide-react';
import { useCallback, useEffect, useState } from 'react';

type VaultUnlockGateProps = {
  locked: boolean;
  needsTotpSetup?: boolean;
  obsidianLocked?: boolean;
  busy: boolean;
  error: string | null;
  qrDataUrl: string | null;
  setupBusy: boolean;
  setupError: string | null;
  onBeginSetup: () => Promise<void>;
  onUnlock: (code: string) => Promise<boolean>;
};

export function VaultUnlockGate({
  locked,
  needsTotpSetup = false,
  obsidianLocked = false,
  busy,
  error,
  qrDataUrl,
  setupBusy,
  setupError,
  onBeginSetup,
  onUnlock,
}: VaultUnlockGateProps) {
  const [code, setCode] = useState('');

  useEffect(() => {
    if (needsTotpSetup && !qrDataUrl && !setupBusy && !setupError) {
      void onBeginSetup();
    }
  }, [needsTotpSetup, qrDataUrl, setupBusy, setupError, onBeginSetup]);

  const handleSubmit = useCallback(async () => {
    if (!code.trim()) {
      return;
    }
    const ok = await onUnlock(code.trim());
    if (ok) {
      setCode('');
    }
  }, [code, onUnlock]);

  if (!locked && !needsTotpSetup) {
    return null;
  }

  return (
    <div className="absolute inset-0 z-40 flex items-center justify-center bg-background/90 backdrop-blur-sm">
      <div className="max-w-md w-full mx-4 rounded-xl border bg-card p-8 shadow-lg text-center space-y-4">
        <KeyRound className="mx-auto h-12 w-12 text-sky-500" />
        <h2 className="text-xl font-semibold">
          {needsTotpSetup
            ? 'Register authenticator app'
            : 'Local vault verification'}
        </h2>
        <p className="text-sm text-text-secondary">
          {needsTotpSetup
            ? 'Scan this QR code with Google Authenticator (or any TOTP app), then enter the 6-digit code to confirm. This unlocks sealed prompts, API keys, and Obsidian mail storage on this device.'
            : 'Enter the 6-digit code from your authenticator app to unlock sealed prompts, API keys, and offline mail storage for this session.'}
        </p>
        {obsidianLocked ? (
          <div className="flex items-center justify-center gap-2 rounded-lg border border-amber-500/40 bg-amber-500/10 px-3 py-2 text-xs text-amber-800 dark:text-amber-200">
            <Lock className="h-3.5 w-3.5 shrink-0" />
            <span>Obsidian mail storage is locked until you verify.</span>
          </div>
        ) : null}
        {needsTotpSetup ? (
          <>
            {setupBusy ? (
              <p className="text-sm text-text-secondary">
                Preparing enrollment QR…
              </p>
            ) : qrDataUrl ? (
              <img
                src={qrDataUrl}
                alt="TOTP enrollment QR code"
                className="mx-auto h-48 w-48 rounded-md border bg-white p-2"
              />
            ) : (
              <p className="text-sm text-destructive">
                QR image unavailable. Check server logs or run{' '}
                <code className="text-xs">init_mail_intel_vault.py</code> on the
                host.
              </p>
            )}
            {setupError ? (
              <p className="text-sm text-destructive">{setupError}</p>
            ) : null}
          </>
        ) : null}
        <Input
          inputMode="numeric"
          autoComplete="one-time-code"
          placeholder="000000"
          value={code}
          maxLength={8}
          onChange={(e) =>
            setCode(e.target.value.replace(/\D/g, '').slice(0, 6))
          }
          className="text-center text-lg tracking-widest"
        />
        {error ? <p className="text-sm text-destructive">{error}</p> : null}
        <Button
          disabled={
            busy ||
            code.length < 6 ||
            (needsTotpSetup && setupBusy && !qrDataUrl)
          }
          onClick={handleSubmit}
          className="w-full"
        >
          {busy
            ? 'Verifying…'
            : needsTotpSetup
              ? 'Confirm & unlock local vault'
              : 'Unlock local vault'}
        </Button>
        {needsTotpSetup && setupError ? (
          <Button
            variant="outline"
            disabled={setupBusy}
            onClick={() => void onBeginSetup()}
            className="w-full"
          >
            Retry enrollment
          </Button>
        ) : null}
      </div>
    </div>
  );
}
