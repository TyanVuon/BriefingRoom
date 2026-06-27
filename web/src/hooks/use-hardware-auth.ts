/**
 * @deprecated Prefer useExploreHardwareAuth inside AgentExplore (HardwareAuthProvider).
 * Re-exported for callers outside explore that may adopt the provider later.
 */
export {
  HardwareAuthProvider,
  useExploreHardwareAuth as useHardwareAuth,
} from '@/pages/agent/explore/hardware-auth-context';
