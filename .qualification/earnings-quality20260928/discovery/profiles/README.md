# Fixed-pool SEC profiles

Capture only the300 ordered current submissions root URLs bound to the frozen pool. Three hundred network starts, one start per URL with no retry, one request/second,8MiBresponse and2GiBnewraw bounds apply. Existing exact root sources are reused; no history file, archive, ticker-map or alternative CIK request is permitted.403/429 and source limits stop globally.

Each raw/source/error result and incomplete pool position remains in source-manifest.json. profiles_by_CIK.json contains the raw current dictionary for a captured matching CIK or null for an unavailable one, ready for cohort.qualify_pool. Qualification and the final100 selection are separate. Shared SEC and own capture locks are held throughout.

Six offline tests pass, covering exact ordered pool binding, URL/budget constraints, cached reuse with zeroGETs, source/CIK failure preservation and corruption checks,403/429/byte ceilings, no interrupted retry, complete output denominator, and lock exclusion. No actual profile request was launched during implementation.
