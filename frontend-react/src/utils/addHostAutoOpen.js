const AUTO_OPEN_ADD_HOST_KEY = 'qlsm:auto-open-add-host';

export function armAutoOpenAddHost() {
  window.sessionStorage.setItem(AUTO_OPEN_ADD_HOST_KEY, '1');
}

export function clearAutoOpenAddHost() {
  window.sessionStorage.removeItem(AUTO_OPEN_ADD_HOST_KEY);
}

export function shouldAutoOpenAddHost(locationState) {
  if (locationState?.openAddHost === true) {
    return true;
  }

  return window.sessionStorage.getItem(AUTO_OPEN_ADD_HOST_KEY) === '1';
}
