// The search page's filters start folded on small screens, so the results come first;
// on wider screens there is room, so open them.
const filters = document.querySelector('.search-form__more');
if (filters && window.matchMedia('(min-width: 40rem)').matches) {
    filters.open = true;
}
