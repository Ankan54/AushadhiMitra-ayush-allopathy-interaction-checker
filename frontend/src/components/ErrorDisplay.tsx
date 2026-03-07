interface Props {
  message: string;
  supportedDrugs?: string[];
}

export default function ErrorDisplay({ message, supportedDrugs }: Props) {
  return (
    <div className="bg-red-900/20 border border-red-800/50 rounded-xl p-5">
      <div className="flex items-start gap-3">
        <span className="text-red-400 text-lg mt-0.5">⚠</span>
        <div className="flex-1 min-w-0">
          <h3 className="text-sm font-semibold text-red-300 mb-1">Unable to Process Request</h3>
          <p className="text-sm text-gray-300">{message}</p>

          {supportedDrugs && supportedDrugs.length > 0 && (
            <div className="mt-4">
              <p className="text-xs font-medium text-gray-400 mb-2">
                Currently supported AYUSH drugs in this demo:
              </p>
              <ul className="space-y-1">
                {supportedDrugs.map((d) => (
                  <li key={d} className="text-xs text-green-300">
                    • {d}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
