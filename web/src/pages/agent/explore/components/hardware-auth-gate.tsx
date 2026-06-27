import { Button } from '@/components/ui/button';
import { ShieldAlert } from 'lucide-react';

type HardwareAuthGateProps = {
  locked: boolean;
  registered: boolean | null;
  needsReprovision?: boolean;
  busy: boolean;
  error: string | null;
  onRegister: () => void;
  onUnlock: () => void;
};

export function HardwareAuthGate({
  locked,
  registered,
  needsReprovision = false,
  busy,
  error,
  onRegister,
  onUnlock,
}: HardwareAuthGateProps) {
  if (!locked) {
    return null;
  }

  const isFirstTime = registered === false;
  const showProvision = isFirstTime || needsReprovision;

  return (
    <div className="absolute inset-0 z-50 flex items-center justify-center bg-background/95 backdrop-blur-sm">
      <div className="max-w-md w-full mx-4 rounded-xl border bg-card p-8 shadow-lg text-center space-y-4">
        <ShieldAlert className="mx-auto h-12 w-12 text-amber-500" />
        <h2 className="text-xl font-semibold">
          {showProvision
            ? needsReprovision
              ? 'HSM re-provisioning required'
              : 'Initial HSM provisioning'
            : 'Module verification required'}
        </h2>
        <p className="text-sm text-text-secondary">
          {showProvision ? (
            needsReprovision ? (
              <>
                The stored module enrollment could not be read (for example
                after a configuration change). Connect your physical module and
                complete re-provisioning to continue.
              </>
            ) : (
              <>
                Zero-trust mode requires a registered hardware security module.
                Connect your physical module and complete enrollment when
                prompted. Access continues automatically after provisioning.
              </>
            )
          ) : (
            <>
              Zero-trust mode: session context was cleared. Authenticate via
              your registered hardware security module to continue.
            </>
          )}
        </p>
        {error ? <p className="text-sm text-destructive">{error}</p> : null}
        {registered === null ? (
          <Button disabled className="w-full">
            Checking module status…
          </Button>
        ) : showProvision ? (
          <Button disabled={busy} onClick={onRegister} className="w-full">
            {busy
              ? 'Awaiting module…'
              : needsReprovision
                ? 'Re-provision HSM module'
                : 'Begin HSM provisioning'}
          </Button>
        ) : (
          <Button disabled={busy} onClick={onUnlock} className="w-full">
            {busy ? 'Awaiting module…' : 'Verify with HSM module'}
          </Button>
        )}
      </div>
    </div>
  );
}
