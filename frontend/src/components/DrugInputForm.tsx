import { useState, useRef } from 'react';

// Exactly the 5 demo-supported AYUSH plants
const DEMO_PLANTS = [
  { scientific: 'Curcuma longa',        common: 'Turmeric / Haldi' },
  { scientific: 'Glycyrrhiza glabra',   common: 'Licorice / Mulethi' },
  { scientific: 'Zingiber officinale',  common: 'Ginger / Adrak' },
  { scientific: "Hypericum perforatum", common: "St. John's Wort" },
  { scientific: 'Withania somnifera',   common: 'Ashwagandha' },
];

interface Props {
  ayushDrug: string;
  allopathyDrug: string;
  onAyushChange: (v: string) => void;
  onAllopathyChange: (v: string) => void;
  onSubmit: () => void;
  isLoading: boolean;
}

export default function DrugInputForm({
  ayushDrug,
  allopathyDrug,
  onAyushChange,
  onAllopathyChange,
  onSubmit,
  isLoading,
}: Props) {
  const [dropdownOpen, setDropdownOpen] = useState(false);
  const ayushRef = useRef<HTMLInputElement>(null);

  const filtered = ayushDrug.trim()
    ? DEMO_PLANTS.filter(
        (p) =>
          p.scientific.toLowerCase().includes(ayushDrug.toLowerCase()) ||
          p.common.toLowerCase().includes(ayushDrug.toLowerCase())
      )
    : DEMO_PLANTS;

  const handleSelect = (plant: typeof DEMO_PLANTS[0]) => {
    onAyushChange(plant.scientific);
    setDropdownOpen(false);
    ayushRef.current?.blur();
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !isLoading && ayushDrug.trim() && allopathyDrug.trim()) {
      setDropdownOpen(false);
      onSubmit();
    }
    if (e.key === 'Escape') setDropdownOpen(false);
  };

  const canSubmit = !isLoading && ayushDrug.trim().length > 0 && allopathyDrug.trim().length > 0;

  return (
    <div className="space-y-3">
      {/* Row 1: two inputs side by side */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        {/* AYUSH input */}
        <div className="relative">
          <label className="block text-xs font-medium text-green-400 mb-1.5 uppercase tracking-wide">
            AYUSH Drug
            <span className="ml-1.5 text-gray-600 normal-case tracking-normal font-normal">
              — demo: 5 plants only
            </span>
          </label>
          <input
            ref={ayushRef}
            type="text"
            value={ayushDrug}
            onChange={(e) => { onAyushChange(e.target.value); setDropdownOpen(true); }}
            onFocus={() => setDropdownOpen(true)}
            onBlur={() => setTimeout(() => setDropdownOpen(false), 160)}
            onKeyDown={handleKeyDown}
            disabled={isLoading}
            placeholder="Click to see available plants…"
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-3 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-green-500 focus:ring-1 focus:ring-green-500/20 disabled:opacity-50 transition"
          />

          {/* Dropdown */}
          {dropdownOpen && (
            <ul className="absolute z-20 top-full mt-1 w-full bg-gray-800 border border-gray-700 rounded-lg shadow-2xl overflow-hidden">
              <li className="px-3 py-1.5 text-xs text-gray-500 bg-gray-900/80 border-b border-gray-700 select-none">
                Available for this demo:
              </li>
              {filtered.length > 0 ? (
                filtered.map((p) => (
                  <li
                    key={p.scientific}
                    onMouseDown={() => handleSelect(p)}
                    className="px-4 py-2.5 text-sm cursor-pointer hover:bg-gray-700 transition-colors flex items-baseline gap-2"
                  >
                    <span className="text-green-300 font-medium italic">{p.scientific}</span>
                    <span className="text-gray-500 text-xs">{p.common}</span>
                  </li>
                ))
              ) : (
                <li className="px-4 py-2.5">
                  <p className="text-xs text-red-400 mb-1">Not found in demo list.</p>
                  <p className="text-xs text-gray-500">Available plants:</p>
                  <ul className="mt-1">
                    {DEMO_PLANTS.map((p) => (
                      <li
                        key={p.scientific}
                        onMouseDown={() => handleSelect(p)}
                        className="text-xs text-green-300 cursor-pointer hover:text-green-200 py-0.5"
                      >
                        • {p.scientific}
                      </li>
                    ))}
                  </ul>
                </li>
              )}
            </ul>
          )}
        </div>

        {/* Allopathy input */}
        <div>
          <label className="block text-xs font-medium text-blue-400 mb-1.5 uppercase tracking-wide">
            Allopathy Drug
          </label>
          <input
            type="text"
            value={allopathyDrug}
            onChange={(e) => onAllopathyChange(e.target.value)}
            onKeyDown={handleKeyDown}
            disabled={isLoading}
            placeholder="e.g. Warfarin, Metformin, Atorvastatin…"
            className="w-full bg-gray-800 border border-gray-700 rounded-lg px-4 py-3 text-sm text-white placeholder-gray-500 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500/20 disabled:opacity-50 transition"
          />
        </div>
      </div>

      {/* Row 2: button right-aligned */}
      <div className="flex justify-end">
        <button
          onClick={() => { setDropdownOpen(false); onSubmit(); }}
          disabled={!canSubmit}
          className="px-8 py-2.5 bg-green-600 hover:bg-green-500 disabled:bg-gray-700 disabled:text-gray-500 text-white font-semibold rounded-lg transition-colors text-sm"
        >
          {isLoading ? (
            <span className="flex items-center gap-2">
              <span className="inline-block w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              Analysing…
            </span>
          ) : (
            'Check Interaction →'
          )}
        </button>
      </div>
    </div>
  );
}
