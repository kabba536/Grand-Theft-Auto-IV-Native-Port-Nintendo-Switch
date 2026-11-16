# GTA4NX optimization continuation, 2026-11-14

Goal: stable30FPS on real Switch, three cores0x7 first. Not achieved. User directed: finish LTO, avoid parameter sweeps without a marked win; prioritize actual audio hotspots and unnecessary waits. Preserve clocks/voltage/memory timings, configurations, saves and other data. No commits/publication.

This report was reconstructed from preserved artifacts/HANDOFF after a local text-encoding write failure. Raw captures, build artifacts, patches, source and console data were unaffected. Explicit UTF-8 is used for this reconstruction.

## Measurement baseline and completed trials

All ordinary windows below use the same bridge teleport, fast-resolve B mode, no GPU/stack/PGO sampling. CPU1785/GPU768/RAM2600MHz, mask0x7. Scene/viewport gates passed unless stated. Window means are diagnostic results, not stable30 or game-wide guarantees. Camera/NPC variation remains a limitation.

| Variant | Window means ms | Interpretation |
|---|---|---|
| f669 control, launch1 |46.543367 /46.628850| |
| f669 control, launch2 |46.832845 /46.590299|Mean46.648840; window SD0.12755, range0.28948ms|
| native2unit LTO0f5c |46.652061 /46.193106|Mean46.423; no marked win, stop LTO tuning|
| actual mixer prefetchf1d2 |48.047673 /46.862645|No gain; REVERSED from source|
| natural SIMD lanes6ead |47.132924 /46.637462|No gain; REVERSED from source|
| armed notificationc09d |46.891233 /46.085640|Mean46.488; no marked win|
| actual11unit PGO5360 |47.145161 /46.584277|Mean46.865; no marked win|
| slot submission diagnostic13321d9e |46.828245|Instrumentation, not optimization|
| vertex UBOecb4 BDA control1 |47.200619|One20s window|
| vertex UBOecb4 ON1 |45.111525 /44.495428|Mean44.803477, preliminary improvement|
| vertex UBOecb4 reverse BDA2 |46.905390 /46.115798|Mean46.510594; improvement remains provisional~4%|

Raw trial directories are under `C:\Users\Dima\.local\share\gta4nx\builds`, named baseline-f669-20261114-r1/r2, lto-0f5cde10-20261114-r1, audio-prefetch-f1d229c1-20261114-r1, audio-lanes-6ead89e6-20261114-r1, armed-notify-c09da652-20261114-r1, pgo-actual-use-5360d708-20261114-r1, slot-submission-13321d9e-20261114-r1, vertex-ubo-ecb4c482-{bda,on}-20261114-r1 and vertex-ubo-ecb4c482-bda-20261114-r2. Check actual directory names/manifests before use.

## Audio source and PGO scope correction

The selected `sub_82199BC8` is in `src/gta4_audio_ramped_mix.cpp` plus header. Native-hooks contains an inactive duplicate. The exact link map `saida_combo/audio-prefetch/link.map` identifies the selected/discarded objects under allow-multiple-definition. Earlier native-hooks zero counters described the inactive duplicate; prior native2unit LTO/PGO did not cover the real mixer.

The prefetch experiment restored hints present in generated guest code. The natural-lane experiment used native float lane order/REV32 inside the loop and restored all14 guest scratch vectors. Neither improved FPS in the then GPU-limited configuration. Both source patches remain experimental artifacts, currently reversed.

`tools/build/verify_audio_mix.py` compiles actual old/new kernels to ARM64 ELF and compares execution with isolated Unicorn2.1.4: prefetch768 pairs, natural lanes3072 pairs. Whole arena,14 vectors,FPSR exact across random/finite/special bits, alias/overlap, FPCR normal/FZ/FZ+DN. Functional emulation, not Switch performance or full-wrapper proof.

Correctly scoped native training16fe covered ramped_mix, switch_audio_fast and native_hooks while retaining8generated profiles. Three stable files/manifest/counter-summary in `...\builds\pgo-actual-audio-training-20261114-r1`: all1008 nativeIDs/CFGs mapped; ramped2/2 executed, switch_audio17/58, native_hooks360/948. Selected mixer positive; duplicate zero. Combined11 profiles `/src/pgo_actual_all`. Strict missing-profile/coverage-mismatch use build5360 passed;731strong hooks/no bypass. See [PGO comparison](pgo-comparison-2026-11-13.md).

## Wait correctness and instrumentation

Original multiwait-address fixes partial WaitAll rollback self-notification/spin; the actual-source host extraction reproduces the old30ms timeout hanging beyond3s and verifies the fix. Extra armed-notify SC arm/recheck/generation handshake skips kernel wakes before enrollment while retaining handle-lock lifetime protection. Host tests include2000 enrollment races,900 semaphore tokens, rollback/timeouts/manual broadcast and deterministic unarmed notification. Host correctness is not Horizon performance proof. Armed variant remains in current source; measured FPS gain was insignificant.

Submission tracker has no shared mutex held during GPU wait. NVK sync releases its mutex before native-fence waiting. Native/UI queue separation policy only applies to MoltenVK; SwitchNVK already shares a graphics queue. Queue-lock/submit are negligible. Do not remove required fences based on wall-time alone.

`v35-bench-slot-submission-timeline.patch` applied zero fuzz.13321d9e joined426/427 frames, no dropped entries: alternating slots0/1, waitID=newNativeID-2, awaited submission age50.293ms plus22.279ms fence, recording17.524ms. Unprofiled5360 joined423/424: fence22.447ms, recording17.542ms, prepare3.399ms, submit0.046ms. Five timeline-analyzer tests passed.

## Confirmed GPU timer unit bug

Cached NVK reports timestampPeriod1ns. Switch timestamps require625/384ns per tick, as [deko3d's conversion](https://github.com/devkitPro/deko3d/blob/master/include/deko3d.h#L1292) specifies. Two independent real-console raw-clock captures confirm it. Earlier GPU27ms/headroom inference is WITHDRAWN. CPU/guest intervals are unaffected.

`v35-bench-gpu-raw-envelope.patch` exports existing raw begin/end queries and valid bits, no additional queries. Raw NRO485184e7782aa0d40a355e664caf9472a91602e8cba6c6edcfd8f61857843f53. Run dirs raw-envelope-485184e7-20261114-r1/r2 contain unmodified CSV/cadence.json,119clean rows each,118clean consecutive pairs:

|Run|CPU cadence ms|GPU cadence at wrong1ns ms|Inferred multiplier|Corrected GPU/CPU elapsed ratio|Native GPU corrected ms|Gap corrected ms|
|---|---:|---:|---:|---:|---:|---:|
|r1|46.355915|28.506743|1.62613858|1.00090127|43.099383|3.297489|
|r2|47.483980|29.172898|1.62767446|0.999956813|44.174942|3.297562|

Both guest gates passed and HOME screenshots were inspected, battery100%. The old c09 compact capture (`compact-c09da652-20261114-r2`) had26.816519 reportedms, actually43.646678ms at625/384; its119clean rows remain preserved. Firstc09 attempt failed endpoint scene probe/pending and was not used as proof.

`analyze_gpu_cadence.py` checks clock metadata, wrap, consecutive IDs/frames and finite positive intervals;4tests pass, including avoiding double scaling. Canonical `source/build_nvk.sh` now reproduces Switch-only corrected timestampPeriod/newFIX_ID. Embedded Python, exact replacement on temporary pinned-source copy, Bash syntax passed. Cached NVK library has NOT been rebuilt/replaced.

`v35-bench-switch-timestamp-period.patch` supplies the same reporting correction for cached SwitchNVK only when its reported period is exactly1ns, avoiding double correction with a fixed driver. Included inD5 onward. No clock/timer registers or system settings changed.

## Compact GPU identities

`v35-bench-compact-gpu-regions.patch` retains only already-timed available/nonzero regions and exports a small run-specific sidecar; no additional queries or detailedCPU tracing. Collector verifies capture/frame/sequence/timing and downloads it;18tests pass.3c647644 capture passed120/119clean and HOME inspected. Only238timed grouped regions: clear0.314ms and VS c195a0a68d7ba860/PS0 single-primitive0.019ms per frame. This is NOT hot-shader coverage; remaining unavailable attribution is not zero. No further broad attribution tracing planned now.

## Isolated constant-bank UBO trials

Aligned-UBO source patch applied zero fuzz. New vertex-only overlay confines benchmark conversion to vertex bank; pixel/shared remain BDA, isolated`.aligned-ubo-vs-only`cache. Marker absent is BDA. All allocation/dynamic-offset checks use device256byte alignment. Live TOML unchanged.

Actual shader-corpus structural validation:639VS modules,12259bank loads;1256PS modules,30758bank loads. Original and rewritten variants passed spirv-val Vulkan1.2 scalar layout. Proof dirs `/src/ubo-corpus-proof`, `/src/ubo-pixel-corpus-proof`; small results copied to ignored candidate output dirs. This is not GPU functional-equivalence proof. Shared-bank proof used a generic block size and is not relied on for functional claims.

Vertex candidate ecb4c482993c318431f12ec5fbcbe28109dd94998fda93b6f40e53a11265fb52, `saida_combo/vertex-only-ubo`, strict11PGO. BDA/ON/reverse controls listed above. Visible images/HOME checked; marker ownership/archive/readback verified. Saved ONstderr proves628rewritten shaders12222loads; BDAstderr0/0. Baseline cache/backend/alias warnings remain, so logs are not universally error-free.

VS-only ON timeline fence4.025/4.536ms, recording20.577/20.168ms, prepare3.396/3.402ms. Reverse BDA fence22.128/21.762, recording17.816/17.457. VS-only recorder-to-submit28.386ms vs full45.112ms. Native wait decreased but recording CPU increased and frame cadence still~45ms. Do not infer GPU below33.33ms from fence alone.

Passive exactec ELF symbolization saved symbols.json/symbolized.log/cpu-steady.json in bothprofiledirs. Seven late report means ON: producer52.8%, recorder47.9, main44.3, DSP43.8, worker26.3, audioengine17.3,XMA13.9,retirer11.0. Producer snapshotCaptureBufferResource, DSP82934F00, main NtWaitForSingleObjectEx. Snapshots are not duration attribution. Main/producer preferredcore1/mask0x7; unchanged. Fresh high-frequency sampling before CPU edits.

## Current D5 trial

VS+PS overlay enables both banks, shared constants still BDA; cache`.aligned-ubo-vs-ps`. Candidate **d5f6cdacb93181314973e8233e9d1396b1eeb4cfeb1db4279d9bb2dab5fc94db**, `saida_combo/vertex-pixel-ubo`, strict11PGO and timestamp workaround. Deployed overecb4 withjournal `...\builds\vertex-pixel-ubo-d5f6cdac\deploy.json`; previous chain preserved.

Current sole console operation: compact-profile-pixel-ubo.py --shaD5 --label vertex-pixel-ubo-d5f6cdac-gpu-20261114-r1, exec43859. BothGPU/UBO markers owned/readback; world/teleport/capture passed.119clean GPU rows: native37.892907ms (corrected metadata), fence0.138627ms, callback28.383112ms, publish29.579186ms, outside renderer17.183918ms. GPU warp-shadow8.866665, resolve8.534774, scene-to-gbuffer6.619422, lights-to-screen3.634318ms. Need inspect gameplay/HOME and marker archives after exit. Still above33.33ms GPU target and CPU frame cadence remains high; no stable30 claim.

Next after safe exit: sample CPU in this exact mode if useful using prepared sample-pixel-ubo.py (UBO+perfil_pilas owned markers, noGPU,one20sB). Symbolize exactD5 ELF. ProfilingFPS is not unprofiled performance evidence. If regression/black/hang, stop bounded trial and retain preserved fallback; no blind retries.

## Persistent safety and live configuration

Console192.168.1.220 FTP5000/sysbot6000, Sphaira03DB163FAA760000. Sole operator root. Cooperatively exit exactSHA and inspect HOME screenshot before next deployment. Charging/full battery, clocks1785/768/2600, mask0x7. User saves/configurations untouched. Native TOML read-only snapshot `...\builds\config-native-20261114-readonly.toml`, SHAa2a193ff9b8e3024fd97652ce5b96b223107cd08f513fad220147241962036f9; UBO flagsfalse, present immediate, no frame-slot override.

Build source `/src/lra35`, SDK underglue/rexglue-sdk-main, Docker volume gta4nx-src, actual graph `/src/build_combo/build-pgo-actual-audio-use.ninja`. Do not run destructive upstream scripts. Canonical cached driver stillnak-unop-flip-v1+sched-latency-peephole-v2; manual builds copy its libvulkan.a. Source contains original audio/noLTO, original+armed multiwait, fastresolve and listed instrumentation/UBO overlays. Experiments reproduced by repo patches. Short windows avoid NPC assault. Stable30 goal remains ACTIVE.

## Fresh CPU profile and natural-mixer retest

D5 stack run completed:9030PCs symbolized against exactD5 ELF, hot-functions.json under `.../vertex-pixel-ubo-d5f6cdac-stack-20261114-r1/rex-profile-m8ikn8od`. Blocks10-14 used as leads; endpoint viewport shows Niko standing, later gameplay-end shows NPC assault, late reports excluded. HOME100% checked, bothmarkers archived/readback. Sampled45.045ms is not ordinary performance proof. ProducerCPU53.9%, recorder48.6, DSP44.3, main43.4, worker25.4,audioengine23.6,XMA14.2. DSP wallPC mixer82199BC8~20%,821997F8~4.7%,82936CE0~4.6. WallPC is not CPUtime. Audioengine svcSleep reaches ordinaryKeDelayExecutionThread; no removal of timed waits. D5main preferredcore0 in a sample, so earlier ec preferredcore1 is not a fixed policy. No affinity/priority changes.

D5 clean unprofiled pair completed45.061400/42.491958ms (mean43.776679); scene/gates/screens/HOME checked. Larger2.57ms within-launch spread than old f669 baseline; small future gains require repetition and camera/NPC caution.

Natural SIMD header reapplied zero fuzz; SHA1e58d289628248ddf49db212cb4a73a4c1ccb7e1ef8a03196f28d2dcfc62713b exactly matches the existing proof manifest. Strict11PGO rejected changed mixerCFG: old3arc counters/new2. Warning not suppressed. New graph `build-pgo-ubo-lanes-use.ninja` retains strict profiles for10other units, excludes onlyramped_mix.cpp. Comparison is combined kernel/PGO-scope change, not isolated SIMD evidence. Header manifest exactmatch checked by script,3072bit-exact emulatedkernel pairs reused; selectedlivefunction14REV32/zeroPRFM verified.

Candidate9ec9a76da5297402b3d71690143e1c4f2d249e1c197aea266a0ebefc7f8bb21c built, `saida_combo/audio-lanes-ubo-pgo10`, provenance.json. Deployed overD5, journal `.../builds/audio-lanes-ubo-9ec9a76d/deploy.json`. Current sole operator paired-pixel-ubo.py --sha9ec --label audio-lanes-ubo-9ec9a76d-clean-20261114-r1, session81201, ordinary2x20s, UBOmarkerowned/noGPUorstack. Inspect completion/gameplay/HOME before nextaction. NaturalpatchAPPLIED in source, latestgraph10PGO. No otherbuildrunning.

Potential later shared-bank study: actual NativeSharedConstants size0x500,80registers, existing thirdUBObinding alreadyaligned/validated. Read-only structural proof rerun on1895VS/PSmodules withactual80registersharedblock: all originals/bank/sharedvariants passspirv-val;43017bankloads/30368sharedloads. `/src/ubo-shared80-corpus-proof/result.json`. Shared GPU path stillDISABLED in currentcandidates; not hardware/functionality proof. Do not revive the old full-UBO black-screen case blindly.

Natural mixer repeat9ec r2 completed43.730923/43.114618ms, HOME/screens checked. Four9ec window means42.684472/42.026170/43.730923/43.114618 average42.889046ms versusD5two-window43.776679ms. Preliminary~2% difference is not established beyond scene/camera noise. Audio state/graphics remain subject to full validation; no stable30claim.

Prepared guest zero-poll policy C6: preserve original kernel yield on first failed poll, then at least every8failedpolls per thread; raised threads always use original protection. Only rawzero timeout after XObject Wait/SignalAndWait/WaitAny/WaitAll timeout is gated. Timed/infinite waits and XThread::Delay unchanged; timeout value captured once before waiting. All successes/APCs/WaitCallbacks unchanged. Host test extracts actual core policy/helper:4threads, bounded7skips, raised bypass, positive/infinite waits, concurrent flag toggling all pass. No Horizon scheduling/FPS proof. `tools/build/verify_guest_poll_yield.py`, coreSHAfd6f2ea318468d7f2aa2c26bcc3411e445add57a6775ab07651b7e9e38fb4d64, XObjectSHAdd377116b38dcc14c77b84dbc66dc2df1f415e1fed55ee7e7f2c0dbb6af50ef9.

Built C6c6d969430126d9c60d845c060b12e3fd53c27581b6190eab90f4407ed1ea3633, `saida_combo/poll-yield-ubo`. DefaultpolicyOFF, startupowned`bench_guest_poll_yield.flag` enables8; captureCSVconfirmsmetadata. Deployment session28486 over9ec, journal `.../builds/poll-yield-c6d96943/deploy.json`. Next run paired-poll-yield.py --shaC6 --label poll-yield-c6d96943-clean-20261114-r1. It ownsUBO+yieldflags and validatesCSVbatch8, archives/readbacks both afterexit. Fivebenchdeploytests pass; deploy now blocks leftoveryieldflag.

Hostsource now INDEPENDENT of C6: guest-poll patch reversed zero-fuzz afterfreezingC6 artifact; all-three UBO overlayAPPLIED (shared bank enabled, cache`.aligned-ubo-all3`), naturalmixer/10PGOretained. Building session59371, graphbuild-pgo-ubo-lanes-use.ninja, NOT deployed. This isolates shared-bank test frompoll-yield change. Do not confuse currentSDKsource withactiveC6. Shared80register proof1895modulespassed, no GPUevidence yet.

C6 deployed successfully and ordinary poll-yield trial is running via paired-poll-yield.py, session86161. Requires both ownedUBO/yieldmarkers and checks captureCSVbatch8. All-bank independent candidate **d03278955a2b51f02b6397fe8fffb5b8e2a08930beb34b1b0e658091a3b7bb52** built/copied/hashchecked, `saida_combo/all-ubo-banks`; NOT deployed. CurrentSDKsource all3banks/nopollpolicy; do not confuse withactiveC6. Later sharedtrial usesaccurateall3runnerlabel and noyieldflag.


C6 poll-yield completed: 43.585255 / 44.492640 ms, mean44.038947 versus9ec pooled42.889046. No demonstrated gain; do not sweep batching parameters. Both CSVs confirmedbatch8; both owned markers archived/readback; gameplay and HOME screenshots inspected. No assault visible at endpoint. Independent all3 candidate d032 deployment in progress, journal builds/all-ubo-d0327895/deploy.json. Hostsource excludes poll policy.

All3 d032 ordinary trial aborted by player-state gate: guest-capture-h78c1enr, displacement2.154829m during first20s, samples435. Prior viewport shows pedestrians surrounding Niko. Not a valid FPS comparison; no renderer hang/black screen. Exit HOME inspected; UBOmarker archived/readback. Next compact-profile-all-ubo.py short10s/120samples is a GPU cost diagnostic, not an ordinary FPS proof. No blind retry on hangs.

All3 d032 GPU diagnostic completed120/119clean: native34.297685ms, fence0.106015, callback26.939884, publish28.232117, outside16.527590. Warp-shadow9.269247, resolve8.514087, sceneGBuf4.777724, lights3.076762. One launch versus D5native37.892907; promising but not repeated FPS evidence. Gameplay/HOME inspected; GPU+UBO markers archived/readback. Savedstderr2460rewritten shaders151731UBOloads.

Observer-only yield-sites patch applied to currentSDKall3/natural/10PGO, canonicalCMakeandexplicitNinjagraphwrapsched_yield. Enabled only by existing stackflag; every64thhostyieldrecords immediatecallsite, bounded64slotatomictable, per-reportexchange and dropcount. Existing guestNtYield/spin counters nowreportedbythreadhandle; spinroundsareNOTyieldcounts. Actual-source host concurrency/sampling/collision/overflowcheckpassed. Diagnostic6148009101b536766dde90ec4d9c95478cb1f99b18ab24c16ffd6ba9a08d879c built/copied saida_combo/yield-sites. Deployment4419 inprogress over d032; next sample-yield-sites.py1x10s, profileFPSnotperformanceevidence. No schedulepolicy/clockchanges.

6148 observer deployed/readback and current stack trial64966 running1x10s. Capture completed42.433741ms; this is instrumented, not ordinary FPS proof. Prepared symbolizer uses exact6148ELF and returnPC-4. Current ConstantSnapshotPool is UNCHANGED: new actual-header stress fixture passed ASan+UBSan with8concurrentrelease threads,30000immutable snapshots,partialcopies and9000heldbuffers/reuse overflow. This only establishes a baseline lifetime check for a possible future wait fix, pending call-site evidence; not a performance change.

6148 stack diagnostic completed42.433741ms (not FPS proof), gameplay/HOME inspected, markers archived/readback. Exactsymbolizer output yield-sites-symbolized.json in rex-profile-cfvk51cl. Reports12-16:20776host samples,19196pool-related=92.395%,0drops; dominant returnPC0x5b3e68 SnapshotCurrentVersion poollock; rare0x56893c deleter. TimerQueue and MaybeYield account forremainder. GuestNtYieldExecution counts0, guestspinrounds largebutnotkernel-yieldcounts. No blanketguestyieldbatchingneeded.

New snapshot-pool return-list candidate replaces per-draw spinlock with single allocating-worker private list and per-bank atomicMPSCreturnlist; only consumerexchange detaches wholelists, producersnever dereferenceoldhead. Node/vector ownership stays with finalsharedptr; per-bank retainedcap8192countsqueued/local/reservations. Banksstableforprocesslifetime. Patch v35-opt-snapshot-pool-returns.patch applied to SDK, graphicsbuild32264 running10PGO/noLTO. Actual-header8release-thread30000snapshot/partialcopy/9000held-cap stress passed ASan+UBSan before and after. TSan unavailable: unexpectedmemorymapping bothnormal/noPIE, no hostsettingschanged. Need hardwarecorrectness+repeatedordinarytimings.

Poolcandidate built7c483b56185fd573f2f3863f4728c761256d3f5d2833455d230eb2416b47bb92, saida_combo/snapshot-pool-returns withprovenance.json. HostNROhashmatches. Not deployed. Ordinary6148control atoldpointfailed playergate again, guest-capture-_3fme9b4; warmupviewport shows activefight, excluded regardlessofFPS. HOMEchecked,markerarchived. Do not blindlyrepeatoldpoint. New comparison runner paired-sidewalk-ubo.py uses(900.78,-521.38,15.04),15m downsamebusystreet; bothcontrolandcandidate mustuseit, numbersnotdirectlycomparabletooldpoint. CoreSDK/clock/settings/saveunchanged. Currentordinarycontrol newpoint starting6148.

Newsidewalk6148controlr1completed45.388831/43.440802ms,p95=54.576042/52.925833,samples441/461,mean44.414817. Bothplayergatespass; warmupviewport-1 andgameplayendclean/standing, HOMEchecked, markerarchive/readback. viewport-0 hadtransienttopoverlay/readbackstripes alsoaffectingoverlay; laterimagesclean, so do not falsely attribute it to the not-deployed poolcandidate. Repeatbaseline r2 now to estimate new-point runnoise beforeone-waycandidate deployment. No stable30claim.

TSan setup resolved without hostsettingschanges: docker networknone, readonlysourcevolume, container-local setarchx86_64-R ran actual snapshot-pool-returns-tsan-nopie successfully. 8release-thread/30000snapshot/partialcopy/9000held-reuse stress passed with no TSan races reported. Earlier mapping failures were tool startup failures, not race results. Candidateprovenance updated. Newpointcontrolr2 exec98807 running unchangedSD6148.

Resume/preflight: console liveHOME inspected, noPythonrunner remaining, activebenchflags empty. Controlr2 secondwindowfailed5.487822mNPCdisplacement; FIRST20s window guest-capture-hx9h7tyg is valid44.085386ms,p95=54.748542,454samples,exactly0mendpointdisplacement. Controlr1first45.388831ms also0mdisplacement. Predeclared PRIMARY comparison beforecandidate: first20swindow perindependentlaunch, bothsameinitialsettle/warmup. Twocontrolfirstmeans44.737108ms, sampleSD0.921675ms; baseline-first-windows.json saved. Candidate runner paired-sidewalk-ubo.py --runs1 avoids lateNPCcontamination; do not weakenplayergate. Candidate7c48 deployment7475 running over6148; predecessor preserved.

GPU capturetool gained optional resolve_swap flag/CLI--resolve-swap, stagesreadbackmarker andrequiresguestCSVconfirmation; resume rejects changedmode. Combinedcompactfastresolve+swap pathhosttested;21capture_gpu_profiletests pass. This onlyprepareslaterGPUcostexperiment, no newconsolemode enabled. FixedoneexistinginvalidCP1252dashbyteandnormalizedLFingpu-profile-notes.md; diffcheckpasses.

Pool7c48ordinaryr1 completed44.671708ms,p95=52.933750,p99=57.954375,samples447; gameplay/HOMEchecked, UBOmarker archived/readback. r2capture completed44.961054ms,p95=54.129948,p99=58.480313;gameplayendinspectedstanding,player0mdisplacementbothruns. r2exit/collection28084 pending verification. Pairmean44.816381 versuscontrol44.737108(+0.079273ms): NOdemonstratedFPSgain. Passive reports12-16 control25911.6yield/s→pool2173.4yield/s, CPUtotal299.4→300.0%; realwaitreductiondoesnottranslateintoframegainhere. Per-handleCPUmeans preserved in passive-comparison-r1.json, unknownthreadnamesnotmerged. ordinary-comparison.json recordsprimarypair. Keepasexperimental, do not claim stable30 or spendtimeonpoolparametersearch. Next boundedGPUcostoff/onresolve-swap using same7c48 andnewpoint; preparedcompact-profile-pool-swap.py plushosttool21testspass.

CPUinactive-probe guard built04f12711adbab52ccffa58a6eb610c23eea8cc59464f0a304e586168b7efc6d1, saida_combo/inactive-light-probes/provenance.json. Sourcepreimage088bd600..., patchzero-fuzzreverse dry-runpassed,96branch/logequivalencecases. Deployment26709 staged/readback passed over7c48, previouspreserved. Currentordinarypaired-sidewalk-ubo.py first1x20s04r1 running; noprofilerflags. Latestlive native.toml SHA stilla2a193ff...exactpreservedbaseline.

Independentread-onlyaudit identified five VkDescriptorImageInfo arrays inPrepareFrameTextures (~20325) zero-initialized then fullyassigned atstartofall26stageiterations. Actual7c48ELFretains5memset624calls; sourcehash/equalityonlynamedfieldssopaddingnotread; keeplifetimes{}andwrites{}. A futureisolatedcandidatecanremoveonlythefive redundant{}; notyetapplied. Indexbindingcacheideaunmeasurednotimplemented. PGOnative-renderer scopesupportaddedtohostgraphgenerator;4tests passforstrictuse/generationruntime/scope/no-overwrite. No rendererPGO build/trainingstarted.

Descriptor-init CPUcandidate appliedon04source: removeonlyfive VkDescriptorImageInfo array{}inPrepareFrameTextures; all26elementsfullassignedbeforefirstread/continue, keys/hash/equalityonlynamedfields, paddingnotread. Preserveimage_lifetimes{}andwrites{}, cached-onlydescriptor_infos{}unchanged. Actualsourceinitializationloop extractedintohostfixture;512inputsetsx5banksx26stagesnamedfieldidentical underASan/UBSan,-Wall-Wextra-Werror. Build22886 running; notonSD. RootSDKsource differsfromfrozen04SD bythispatch. Independentread-onlyagent modifiednofilesandneverusedconsole.

ScopedrendererPGOgenerationgraphcreated/verified (NOTbuilt): /src/build_combo/build-pgo-native-renderer-gen.ninja, exactlyonegeneratedSDKgraphics_system.cppobject, tenexistingappprofile-useobjects unchanged, startupPGOdumpenabled. --native-renderernewtool4tests pass. Thispreparesatargetedtestfortheactualrecorder, whicholderPGOpilotsdidnotcover; noLTOsweep. Do not buildgenerationuntildescriptorcandidate22886isfrozen/copied, becauseobjectpathsare shared.

CPU continuation04:41UTC: 04 guard r1 passed43.5952374454ms; r2 excluded by player gate3.728294m endpoint displacement, guest-capture-nhvdrtg3. r2 exit HOME inspected and marker cleanup completed. r3 running session68261, same first20s sidewalk protocol. No speed claim from single clean run. Descriptor9da487d0e1dffeaac7ce65c8c008388bfbc71201159f9d54b51ffad895c70081 frozen with provenance; selected PrepareFrameTextures ELF memset calls9 to4, removing exactly5 redundant624B initializations. Actual-loop512sets x5banks x26stages ASan/UBSan check and zero-fuzz reverse dry-run passed. Renderer generation build completed/frozen7e6fabc7bdd0be5b93f76092c7996c3bdbb380a7d397631c773b48e029bde665, saida_combo/native-renderer-pgo-gen; exactlyoneSDKgenerationobject, tenappuseobjectsretained; no training/deployment yet. Prepared train-native-renderer.py with owned UBO/dump markers and archive/readback. Source frozen b8676661... until matching training/use.

04guard ordinary r3 completed44.0721972728ms; pairedcleanmean43.8337173591 versus7c48mean44.8163810531 (-2.19%, preliminary). r3gameplay/HOME inspected; markersarchived/readback. 04r2excluded3.728294mdisplacement. Deployment68188 staging9da over04 withbackupjournal descriptor-info-init-9da487d0. Twoisolatedworkareas authorized for offline prototypes only: surface-memo-work (explicitlocalmemo+virtualshapeepoch; reflectionrecorder_syncinvariant; clearpendingrelease) and audio-sync-work (removeonlyunusedr23-r30/f26-f31syncattwoleafcalls; preserver31/cr6/xer/vectors). No liveSDKedits/buildsallowedbythoseagents; sourcefrozenforrendererPGO. FPCRforcewriteleadnotimplemented, needsstrictcontractproof.

Descriptor9da first ordinary trial89157 failed: claimed capture timeout guest-capture-asbod5op and cooperative exit30s failed. Fresh screen showed game fight/GPU0/oneCPU99; HOME worked. One HOME/X/observed Close/A closed Sphaira, confirmed processfalse. Systemalive. Copied logs rex_stderr88945B/rex_perfil400583B with hashes in incident-preservation.json; TOML stilla2a193ff..., ownedUBO+pendingexit archived/readback; activeflags empty. No FPS result/no causality established. No repeated9da trial; descriptor patch reversed exactly to04 source2155f359..., 9da anddependent7egen quarantined.
Memo isolated prototype root-reviewed, exactpatchappliedon04. Fullnormal10PGO build86224 passed, frozen813b02511b1b229ca382eb947621f63ed4807307eb10b05246e06657691a484d, saida_combo/surface-lookup-memo/provenance.json. Still oldaudio41374... and fivezeroarraysrestored. CPP7b7561e5.../headerfd9119e3..., patcha3fb11d1.... ActualELFpthreaddefault131072B, RecordFrameframe35296→39392B (+4096); this isstaticframechecknotmaximumcallstackproof. Deployment90859 stagingoverquarantined9da withbackups.
Afterfreezing813 ONLY, audio-leaf-sync applied actualaudio22a5ed8ff0aef0e04ab29912b32dea07bcff9023ac34a720b68751fbc8473e2b. Actualstrict10PGO build rejectedchangedsub821997F8CFG, no warningssuppressed. Createdexplicitbase9graphremovingonlyoldaudioPGO flags, retains8generated+nativehooks; derivedgen graphbuild-pgo-recorder-audio-sync-gen.ninja instrumentsgraphics_system.cpp+switch_audio_fast.cpp,9olduses unchanged, graphscopeJSON inbuildcombo. Build74471 running; newprofiledir /switch/gta4nx/pgo/recorder-audio-sync. No trainingyet, sourcefrozenfornewgeneration. Oldtrain-native-renderer.py hardcoded7e MUSTNOTRUN. Offline fullcaller512pairs+negativecontrol passed; hardwareaudio untested.

## Итоги при остановке пользователем — 14 ноября 2026

Цель поставлена на паузу. Стабильные30FPS не достигнуты; новых тестов после текущего запуска не начинали. Финальный актуальный статус и точные хеши находятся в HANDOFF; предыдущие записи этого отчёта хронологические.

- Два чистых04 замера43.595237/44.072197ms, среднее43.833717ms (~22.8FPS), против7c48mean44.816381. Предварительная разница−2.19%; шум сцены не исключён.04r2 с3.728294m смещения исключён.
- Memo813b первый замер87932 исключён:6.014294m смещения, guest-capture-3nm6w82k. Штатный выход сработал, HOME проверен, маркер архивирован/readback; зависания не было. Нет FPS-результата. Исходники memo возвращены к04 для паузы.
-9da descriptor-init: claimed capture timeout и отказ штатного выхода; система отвечала. Через HOME/Close остановлено приложение. Причина неизвестна, повторов нет. Полные логи и9daELF сохранены; удаление обнулений отменено.
- Audio leaf-sync:512 fullcaller differential pairs и отрицательный контроль прошли, но реальная строгая PGO-сборка отвергла прежний профиль. Патч для паузы отменён, готовая новая2unit-generation20fe сохранена без обучения. Девять прежних use-units оставлены, инструментируются только renderer+audio. Working-set-zero — отдельный не применённый прототип с133639Assign differential cases.
- Источники SDK возвращены в точные04хеши, новаяNRO/ELF20fe не соответствуют этим возвращённым исходникам без повторного применения двух патчей. Сборки/runner остановлены. На SD возвращена04 с полным чтением (`deploy_verified`); процесс Sphaira отсутствует, финальный HOME проверен, активных benchmark flags нет, timeline marker архивирован с readback. Итоговый journal/final-state.json: wrapup-restore-04f12711-20261114.
- Exact04ELF показал CPU299.4%; producer/main на разныхpreferredcores. Доказательств для смены placement нет. CommandRetirer11.48%core — lead на recycle/destruction, не доказанный лишний wait.
- Удалены только unused7egen NRO/ELF201379565B и промежуточные изолированные копии. Manifest/hashes, финальные fixtures, неудачный9daELF, baseline/candidateartifacts, логи и consolebackups сохранены. Чужие изменения не затронуты; commit/publish не выполнялись.
