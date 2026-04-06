// Maps specific Quake Live map names to static preview filenames.
// Files live at: frontend-react/public/map-previews/standard/<filename>.
// This registry is for aliases/overrides; non-workshop maps also fall back to <mapName>.webp.
const standardMapPreviews = {
    campgrounds: 'campgrounds.webp',
    bloodrun: 'bloodrun.webp',
    aerowalk: 'aerowalk.webp',
    toxicity: 'toxicity.webp',
    quartzandsilver: 'quartzandsilver.webp',
};

export default standardMapPreviews;
