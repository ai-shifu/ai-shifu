// import { getPasswordStrengthColor, getPasswordStrengthText } from "@/lib/validators"

interface PasswordStrengthIndicatorProps {
  score?: number;
  feedback: string[];
}

export function PasswordStrengthIndicator({
  score,
  feedback,
}: PasswordStrengthIndicatorProps) {
  console.log('score', score);
  // const strengthText = getPasswordStrengthText(score)
  // const strengthColor = getPasswordStrengthColor(score)

  return (
    <div className="space-y-2">
      {/* <div className="flex items-center justify-between">
        <div className="flex-1 h-2 bg-gray-200 rounded-full overflow-hidden">
          <div
            className={`h-full ${strengthColor} transition-all duration-300`}
            style={{ width: `${Math.max(5, (score / 4) * 100)}%` }}
          />
        </div>
        <span className="text-xs ml-2 min-w-[60px] text-right">{strengthText}</span>
      </div> */}
      {feedback.length > 0 && (
        <ul className="text-xs text-red-500 space-y-1">
          {feedback.map((item, index) => (
            <li key={index}>{item}</li>
          ))}
        </ul>
      )}
    </div>
  );
}
