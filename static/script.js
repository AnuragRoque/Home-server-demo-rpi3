// Camera popup logic
function openCameraPopup() {
  document.getElementById('cameraPopup').style.display = 'flex';
}
function closeCameraPopup() {
  document.getElementById('cameraPopup').style.display = 'none';
}

// Tab switching logic (updated for modern tabs)
const tabLive = document.getElementById('tab-live');
const tabTable = document.getElementById('tab-table');
const contentLive = document.getElementById('tab-content-live');
const contentTable = document.getElementById('tab-content-table');
tabLive.onclick = function() {
  contentLive.style.display = '';
  contentTable.style.display = 'none';
  tabLive.classList.add('active');
  tabTable.classList.remove('active');
};
tabTable.onclick = function() {
  contentLive.style.display = 'none';
  contentTable.style.display = '';
  tabLive.classList.remove('active');
  tabTable.classList.add('active');
};
// Default to live tab
tabLive.click();

// Table sorting/filtering/pagination logic
const table = document.getElementById('main-data-table');
const tbody = document.getElementById('table-body');
const filterDate = document.getElementById('filter-date');
const filterGas = document.getElementById('filter-gas');
const filterMotion = document.getElementById('filter-motion');
const rowsPerPageSelect = document.getElementById('rows-per-page');
const paginationDiv = document.getElementById('table-pagination');

// Parse table data into JS array
let originalRows = [];
Array.from(tbody.rows).forEach(row => {
  originalRows.push(Array.from(row.cells).map(cell => cell.textContent));
});

let filteredRows = [...originalRows];
let currentSort = {col: null, dir: null};
let currentPage = 1;
let rowsPerPage = parseInt(rowsPerPageSelect.value);

function renderTable() {
  // Pagination
  let totalRows = filteredRows.length;
  let pageRows;
  if (rowsPerPageSelect.value === "all") {
    pageRows = filteredRows;
  } else {
    let start = (currentPage - 1) * rowsPerPage;
    pageRows = filteredRows.slice(start, start + rowsPerPage);
  }
  tbody.innerHTML = "";
  for (const row of pageRows) {
    const tr = document.createElement('tr');
    row.forEach((cell, idx) => {
      const td = document.createElement('td');
      td.textContent = cell;
      tr.appendChild(td);
    });
    tbody.appendChild(tr);
  }
  // Pagination controls
  paginationDiv.innerHTML = "";
  if (rowsPerPageSelect.value !== "all") {
    let totalPages = Math.ceil(totalRows / rowsPerPage);
    for (let i = 1; i <= totalPages; i++) {
      const btn = document.createElement('button');
      btn.textContent = i;
      btn.style.background = i === currentPage ? "#2952a3" : "#1a2233";
      btn.style.color = "#e0e6ed";
      btn.style.border = "none";
      btn.style.borderRadius = "6px";
      btn.style.padding = "4px 12px";
      btn.style.margin = "0 2px";
      btn.style.cursor = "pointer";
      btn.onclick = () => { currentPage = i; renderTable(); };
      paginationDiv.appendChild(btn);
    }
  }
}

function applyFiltersAndSort() {
  // Date filter
  let dateVal = filterDate.value;
  // Gas/Motion filter
  let gasVal = filterGas.value;
  let motionVal = filterMotion.value;
  filteredRows = originalRows.filter(row => {
    let match = true;
    if (dateVal) {
      match = match && row[0].startsWith(dateVal);
    }
    if (gasVal !== "") {
      match = match && ((gasVal === "1" && row[4] === "Yes") || (gasVal === "0" && row[4] === "No"));
    }
    if (motionVal !== "") {
      match = match && ((motionVal === "1" && row[5] === "Yes") || (motionVal === "0" && row[5] === "No"));
    }
    return match;
  });
  // Sorting
  if (currentSort.col !== null) {
    filteredRows.sort((a, b) => {
      let v1 = a[currentSort.col];
      let v2 = b[currentSort.col];
      // Numeric sort for temp/hum/aqi
      if (currentSort.col === 1 || currentSort.col === 2 || currentSort.col === 3) {
        v1 = v1 === "--" ? -Infinity : parseFloat(v1);
        v2 = v2 === "--" ? -Infinity : parseFloat(v2);
      }
      if (v1 < v2) return currentSort.dir === "asc" ? -1 : 1;
      if (v1 > v2) return currentSort.dir === "asc" ? 1 : -1;
      return 0;
    });
  }
  // Reset to page 1 if filters/sort change
  currentPage = 1;
  renderTable();
}

// Event listeners
filterDate.onchange = applyFiltersAndSort;
filterGas.onchange = applyFiltersAndSort;
filterMotion.onchange = applyFiltersAndSort;
rowsPerPageSelect.onchange = function() {
  rowsPerPage = rowsPerPageSelect.value === "all" ? filteredRows.length : parseInt(rowsPerPageSelect.value);
  currentPage = 1;
  renderTable();
};
document.querySelectorAll('.sort-btn').forEach(btn => {
  btn.onclick = function() {
    currentSort.col = parseInt(btn.getAttribute('data-col'));
    currentSort.dir = btn.getAttribute('data-dir');
    applyFiltersAndSort();
  };
});

// Live update polling for sensor data
function updateLiveData() {
  fetch('/api/latest')
    .then(res => res.json())
    .then(data => {
      // Indoor
      document.getElementById('indoor-time').textContent = data.latest.time;
      document.getElementById('indoor-temp').textContent = data.latest.temperature;
      document.getElementById('indoor-hum').textContent = data.latest.humidity;
      document.getElementById('indoor-aqi').textContent = data.latest.aqi;
      // Outdoor
      document.getElementById('outdoor-temp').textContent = data.outdoor.temperature;
      document.getElementById('outdoor-hum').textContent = data.outdoor.humidity;
      document.getElementById('outdoor-aqi').textContent = data.outdoor.aqi;
      // Safety
      document.getElementById('last-gas-ago').textContent = "Last " + data.last_gas_ago;
      document.getElementById('last-motion-ago').textContent = "Last " + data.last_motion_ago;
    })
    .catch(() => {});
}
setInterval(updateLiveData, 5000); // Update every 5 seconds

// Initial render
applyFiltersAndSort();
