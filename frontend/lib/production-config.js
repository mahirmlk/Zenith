const REQUIRED_PUBLIC_URLS = [
  'NEXT_PUBLIC_API_URL',
  'NEXT_PUBLIC_SUPABASE_URL',
];

/**
 * @param {{
 *   NEXT_PUBLIC_API_URL?: string,
 *   NEXT_PUBLIC_SUPABASE_URL?: string,
 *   NEXT_PUBLIC_SUPABASE_ANON_KEY?: string
 * }} environment
 */
function validateProductionBuildEnvironment(environment = process.env) {
  const missing = [
    ...REQUIRED_PUBLIC_URLS.filter((name) => !environment[name]?.trim()),
    ...(!environment.NEXT_PUBLIC_SUPABASE_ANON_KEY?.trim()
      ? ['NEXT_PUBLIC_SUPABASE_ANON_KEY']
      : []),
  ];
  if (missing.length > 0) {
    throw new Error(
      `Production frontend build requires: ${missing.join(', ')}. ` +
        'Set these public API/Auth values in the deployment build environment.',
    );
  }

  for (const name of REQUIRED_PUBLIC_URLS) {
    let parsed;
    try {
      parsed = new URL(environment[name]);
    } catch {
      throw new Error(`${name} must be an absolute HTTPS URL.`);
    }
    if (
      parsed.protocol !== 'https:' ||
      !parsed.hostname ||
      parsed.username ||
      parsed.password
    ) {
      throw new Error(`${name} must be an absolute HTTPS URL without credentials.`);
    }
  }
}

module.exports = { validateProductionBuildEnvironment };
