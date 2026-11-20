import { validateProductionBuildEnvironment } from '@/lib/production-config';

const validEnvironment = {
  NEXT_PUBLIC_API_URL: 'https://api.example.invalid',
  NEXT_PUBLIC_SUPABASE_URL: 'https://project.example.invalid',
  NEXT_PUBLIC_SUPABASE_ANON_KEY: 'ci-placeholder',
};

describe('production frontend build configuration', () => {
  it.each([
    'NEXT_PUBLIC_API_URL',
    'NEXT_PUBLIC_SUPABASE_URL',
    'NEXT_PUBLIC_SUPABASE_ANON_KEY',
  ])('requires %s to be present', (name) => {
    const environment = { ...validEnvironment, [name]: '  ' };

    expect(() => validateProductionBuildEnvironment(environment)).toThrow(name);
  });

  it.each(['NEXT_PUBLIC_API_URL', 'NEXT_PUBLIC_SUPABASE_URL'])(
    'rejects non-HTTPS %s values',
    (name) => {
      const environment = { ...validEnvironment, [name]: 'http://example.invalid' };

      expect(() => validateProductionBuildEnvironment(environment)).toThrow(
        'absolute HTTPS URL',
      );
    },
  );

  it('rejects URLs that embed credentials', () => {
    const environment = {
      ...validEnvironment,
      NEXT_PUBLIC_API_URL: 'https://user:password@api.example.invalid',
    };

    expect(() => validateProductionBuildEnvironment(environment)).toThrow(
      'without credentials',
    );
  });

  it('accepts HTTPS test or production values', () => {
    expect(() => validateProductionBuildEnvironment(validEnvironment)).not.toThrow();
  });
});
