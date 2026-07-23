import { cn } from '../../../lib/cn'

/**
 * The Channel Type selector shared by the per-channel S2 canvases. Options are
 * ALWAYS passed in from data (distinct model objects) — never hardcoded. The
 * empty value means "All channels" (the collapsed cross-channel view).
 */
export function ChannelTypeSelect({
  options,
  value,
  onChange,
  label = 'Channel',
}: {
  options: string[]
  value: string
  onChange: (next: string) => void
  label?: string
}) {
  if (!options.length) return null
  return (
    <details className="relative">
      <summary
        className={cn(
          'flex cursor-pointer list-none items-center gap-1 rounded-md border px-2.5 py-1 text-xs transition-colors',
          value
            ? 'border-primary/40 bg-primary/5 text-primary'
            : 'border-border text-muted-foreground hover:bg-muted',
        )}
      >
        {label}
        <span className="max-w-24 truncate text-[11px]">· {value || 'All channels'}</span>
      </summary>
      <div className="absolute z-20 mt-1 max-h-56 w-56 overflow-y-auto rounded-md border border-border bg-popover p-1 shadow-lg">
        <button
          type="button"
          onClick={() => onChange('')}
          className={cn(
            'w-full rounded px-2 py-1 text-left text-xs hover:bg-muted',
            !value && 'font-medium text-primary',
          )}
        >
          All channels
        </button>
        {options.map((o) => (
          <button
            key={o}
            type="button"
            onClick={() => onChange(o)}
            className={cn(
              'w-full truncate rounded px-2 py-1 text-left text-xs hover:bg-muted',
              value === o && 'font-medium text-primary',
            )}
            title={o}
          >
            {o}
          </button>
        ))}
      </div>
    </details>
  )
}
