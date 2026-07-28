import { useEffect, useState } from 'react';

/**
 * Loads a list of options (models, roles…) once on mount.
 * Mirrors the vanilla populate-select pattern, error included.
 */
export function useOptions(loader: () => Promise<string[]>) {
  const [options, setOptions] = useState<string[]>([]);
  const [error, setError] = useState(false);

  useEffect(() => {
    let alive = true;
    loader()
      .then((values) => { if (alive) setOptions(values); })
      .catch(() => { if (alive) setError(true); });
    return () => { alive = false; };
  }, [loader]);

  return { options, error };
}
