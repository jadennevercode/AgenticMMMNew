import { useSimStore } from '../../store/useSimStore'
import { ARTIFACTS } from '../../lib/artifacts-data'
import { AssetList, AssetDetail } from './ArtifactsPanel'

/** Full-page artifact library — list + detail side by side */
export default function AssetsView() {
  const artifacts = useSimStore((s) => s.artifacts)
  const selectedAssetId = useSimStore((s) => s.selectedAssetId)
  const selectAsset = useSimStore((s) => s.selectAsset)
  const current = artifacts.find((a) => a.id === selectedAssetId) ?? artifacts.at(-1) ?? null

  return (
    <div className="flex h-[calc(100vh-3.25rem)] flex-col">
      <div className="flex items-center justify-between border-b border-border px-6 py-3">
        <div>
          <p className="font-mono text-[10px] uppercase tracking-[0.16em] text-muted-foreground">Everything produced</p>
          <h2 className="text-xl font-semibold tracking-tight">Assets</h2>
        </div>
        <span className="font-mono text-[11px] text-muted-foreground">{artifacts.length}/{ARTIFACTS.length} produced</span>
      </div>
      <div className="flex min-h-0 flex-1">
        <div className="w-[300px] shrink-0 border-r border-border">
          <AssetList onPick={selectAsset} selectedId={current?.id ?? null} />
        </div>
        <div className="min-w-0 flex-1">
          {current ? (
            <AssetDetail asset={current} onPick={selectAsset} />
          ) : (
            <p className="grid h-full place-items-center px-6 text-center text-sm text-muted-foreground">
              Nothing produced yet — run the project and documents appear here.
            </p>
          )}
        </div>
      </div>
    </div>
  )
}
