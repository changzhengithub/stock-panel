/** Only the known internal browse routes may become a stock's return target. */
export function browseOrigin(value: unknown): string {
  if (
    typeof value !== "string" ||
    !/^\/(?:market|hot-sectors|industry-chains)(?:[/?]|$)/.test(value)
  )
    return "/market";
  try {
    const url = new URL(value, "https://local.invalid");
    if (
      url.origin !== "https://local.invalid" ||
      !/^(?:\/market|\/hot-sectors(?:\/EM-(?:concept|industry)-BK\d+)?|\/industry-chains(?:\/[a-z0-9][a-z0-9-]{1,63}(?:\/compare)?)?)$/.test(
        url.pathname,
      )
    )
      return "/market";
    return url.pathname + url.search;
  } catch {
    return "/market";
  }
}
