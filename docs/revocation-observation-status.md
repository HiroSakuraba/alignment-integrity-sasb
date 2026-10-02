# Branch status

Branch: `experiment/revocation-observation-semantics`

Purpose: prepare and validate the revocation observation-semantics experiment without live model calls.

Safety/cost status: offline only. The dedicated workflow disables the SASB network interlocks and requires no provider credentials.

Nothing on this branch should be merged until the full existing unit suite and the focused offline probe pass in CI and the diff is reviewed.
