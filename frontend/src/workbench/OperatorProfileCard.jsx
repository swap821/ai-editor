import { useEffect, useState } from 'react';
import { User } from 'lucide-react';
import { fetchOperatorModel } from '../superbrain/lib/aiosAdapter';
import './OperatorProfileCard.css';

const EMPTY_MODEL = { preferences: [], attributes: {}, projectContext: [] };

function titleCase(value) {
  return String(value || '').replace(/_/g, ' ').replace(/\b\w/g, (m) => m.toUpperCase());
}

export default function OperatorProfileCard() {
  const [model, setModel] = useState(EMPTY_MODEL);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let alive = true;
    setLoading(true);
    fetchOperatorModel().then((data) => {
      if (alive) setModel(data);
    }).finally(() => {
      if (alive) setLoading(false);
    });
    return () => {
      alive = false;
    };
  }, []);

  const preferences = model.preferences || [];
  const attributeEntries = Object.entries(model.attributes || {});
  const projectContext = model.projectContext || [];
  const isEmpty = !loading
    && preferences.length === 0
    && attributeEntries.length === 0
    && projectContext.length === 0;

  return (
    <aside className="operator-profile-card" aria-label="Operator profile">
      <div className="operator-profile-card__header">
        <User size={14} aria-hidden="true" />
        <h2>Operator</h2>
      </div>

      {isEmpty ? (
        <div className="operator-profile-card__empty">No operator model yet</div>
      ) : (
        <div className="operator-profile-card__body">
          {preferences.length > 0 ? (
            <section className="operator-profile-card__section">
              <h3>Preferences</h3>
              <ul>
                {preferences.map((fact, i) => (
                  <li key={`${fact.predicate}-${fact.object}-${i}`}>
                    <span className="operator-profile-card__predicate">{titleCase(fact.predicate)}</span>
                    <span className="operator-profile-card__object">{fact.object}</span>
                  </li>
                ))}
              </ul>
            </section>
          ) : null}

          {attributeEntries.length > 0 ? (
            <section className="operator-profile-card__section">
              <h3>About You</h3>
              <ul>
                {attributeEntries.map(([name, value]) => (
                  <li key={name}>
                    <span className="operator-profile-card__predicate">{titleCase(name)}</span>
                    <span className="operator-profile-card__object">{value}</span>
                  </li>
                ))}
              </ul>
            </section>
          ) : null}

          {projectContext.length > 0 ? (
            <section className="operator-profile-card__section">
              <h3>Project</h3>
              <ul>
                {projectContext.map((fact, i) => (
                  <li key={`${fact.predicate}-${fact.object}-${i}`}>
                    <span className="operator-profile-card__predicate">{titleCase(fact.predicate)}</span>
                    <span className="operator-profile-card__object">{fact.object}</span>
                  </li>
                ))}
              </ul>
            </section>
          ) : null}
        </div>
      )}
    </aside>
  );
}
