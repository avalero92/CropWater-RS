# CropWater-RS v2.0.0 — publication checklist

## Synchronize software and documentation

- [ ] Publish the validated v2.0.0 PySide6 source tree on the intended branch.
- [ ] Verify source entry point, dependencies, package metadata and `APP_VERSION` all identify v2.0.0.
- [ ] Verify the Windows installer and executable match the source/release being published.
- [ ] Review the Group A documentation draft and remove synchronization notices once the public code matches v2.0.0.
- [ ] Complete Group B scientific consistency review of `docs/QUANT_METHOD.md`, `docs/KC_NDVI_LIBRARY.md` and the coefficient-library JSON metadata.

## Verify functionality and provenance

- [ ] Reconfirm that the validated v2.0.0 tests and sample workflows correspond to the published source.
- [ ] Check `.cwrs` save/reopen, NDVI acquisition, QC, reconstruction, QUANT, water analysis and exports.
- [ ] Confirm the actual release date and record it consistently in CHANGELOG and CITATION.cff.
- [ ] Check README links, logo rendering, documentation paths and installation guidance.
- [ ] Confirm no CDSE credentials or private data are included.

## Release and archive

- [ ] Check whether a `v2.0.0` tag/release already exists before creating one.
- [ ] Ensure the release includes the correct Windows installer and release notes.
- [ ] Verify Zenodo version-record DOI and preserve the existing concept DOI.
- [ ] Align GitHub citation metadata, `.zenodo.json` and archived release metadata.
- [ ] Review final diff and commit only after all above checks pass.
