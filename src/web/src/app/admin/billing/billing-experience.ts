export function isGlobalBillingExperience(
  paymentChannels: readonly string[] | null | undefined,
): boolean {
  const normalizedChannels = new Set(
    (paymentChannels || [])
      .map(channel => channel.trim().toLowerCase())
      .filter(Boolean),
  );

  return normalizedChannels.size === 1 && normalizedChannels.has('stripe');
}
