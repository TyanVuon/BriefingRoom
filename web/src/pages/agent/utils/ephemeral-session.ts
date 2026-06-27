type AgentPrivacy = {
  ephemeral_sessions?: boolean;
  hardware_auth_required?: boolean;
  zero_trust?: boolean;
  local_vault_required?: boolean;
  obsidian_2fa?: boolean;
};

type AgentDsl = {
  globals?: {
    privacy?: AgentPrivacy;
  };
};

export type PrivacyPolicy = {
  ephemeralSessions: boolean;
  hardwareAuthRequired: boolean;
  zeroTrust: boolean;
  localVaultRequired: boolean;
  obsidian2fa: boolean;
};

export function readPrivacyPolicy(dsl?: AgentDsl | null): PrivacyPolicy {
  const privacy = dsl?.globals?.privacy;
  return {
    ephemeralSessions: privacy?.ephemeral_sessions === true,
    hardwareAuthRequired: privacy?.hardware_auth_required === true,
    zeroTrust: privacy?.zero_trust === true,
    localVaultRequired:
      privacy?.local_vault_required === true || privacy?.zero_trust === true,
    obsidian2fa: privacy?.obsidian_2fa === true || privacy?.zero_trust === true,
  };
}

export function ephemeralSessionsEnabled(dsl?: AgentDsl | null): boolean {
  return readPrivacyPolicy(dsl).ephemeralSessions;
}

export function hardwareAuthRequired(dsl?: AgentDsl | null): boolean {
  return readPrivacyPolicy(dsl).hardwareAuthRequired;
}

export function zeroTrustEnabled(dsl?: AgentDsl | null): boolean {
  return readPrivacyPolicy(dsl).zeroTrust;
}
