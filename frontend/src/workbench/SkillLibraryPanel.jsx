import { useState, useEffect } from 'react';
import { fetchSkills } from '../superbrain/lib/aiosAdapter';

export default function SkillLibraryPanel() {
  const [skills, setSkills] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let mounted = true;
    fetchSkills().then((data) => {
      if (mounted) {
        setSkills(data);
        setLoading(false);
      }
    });
    return () => { mounted = false; };
  }, []);

  return (
    <div className="gagos-panel">
      <h3>Skill Applicability Engine</h3>
      {loading ? (
        <p>Loading skills...</p>
      ) : skills.length === 0 ? (
        <p>No known skills available.</p>
      ) : (
        <ul>
          {skills.map((s, index) => (
            <li key={s.id || s.name || `skill-${index}`}>
              <strong>{s.name}</strong>
              <small> - {s.status}</small>
              <p>{s.description}</p>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}
