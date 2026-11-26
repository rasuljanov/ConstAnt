<script setup>
defineProps({ name: { type: String, required: true }, size: { type: Number, default: 20 } });
const paths = {
  plus: 'M12 5v14M5 12h14',
  ant: 'M14.5 5.5a2.5 2.5 0 1 1-5 0 2.5 2.5 0 0 1 5 0ZM14 11a2 2 0 1 1-4 0 2 2 0 0 1 4 0ZM15 18c0 2.2-1.3 4-3 4s-3-1.8-3-4 1.3-4 3-4 3 1.8 3 4ZM12 8v1m0 4v1M10.5 3.5 8 1M13.5 3.5 16 1M10 10 6 7 3 8M10 12H5l-2 2M10 14l-4 3-3-1M14 10l4-3 3 1M14 12h5l2 2M14 14l4 3 3-1',
  send: 'm6 10 6-6 6 6M12 4v16',
  arrow: 'M7 17 17 7M7 7h10v10',
  back: 'm12 5-7 7 7 7M5 12h14',
  forward: 'm12 5 7 7-7 7M5 12h14',
  upload: 'M12 16V3m-5 5 5-5 5 5M4 16v5h16v-5',
  menu: 'M4 6h16M4 12h16M4 18h16',
  settings: 'M4 7h8m4 0h4M4 17h4m4 0h8M12 4v6M8 14v6',
  account: 'M15.25 8.5a3.25 3.25 0 1 1-6.5 0 3.25 3.25 0 0 1 6.5 0ZM5.5 20v-1a6.5 6.5 0 0 1 13 0v1',
  resources: 'm3 7 9-4 9 4-9 4-9-4Zm0 5 9 4 9-4M3 17l9 4 9-4',
  globe: 'M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0ZM3 12h18M12 3a17 17 0 0 1 0 18 17 17 0 0 1 0-18Z',
  chevron: 'm8 10 4 4 4-4',
  copy: 'M8 8V5a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2h-3M5 8h9a2 2 0 0 1 2 2v9a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-9a2 2 0 0 1 2-2Z',
  clock: 'M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0ZM12 7v5l3 2',
  folder: 'M3 7V5a2 2 0 0 1 2-2h5l2 3h7a2 2 0 0 1 2 2v11a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7Z',
  file: 'M14 2H5v20h14V7l-5-5Zm0 0v5h5M8 12h8M8 16h8',
  image: 'M5 3h14a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2Zm-2 14 5-5 4 4 3-3 6 6M8 7h.01',
  video: 'M3 5h12v14H3V5Zm12 4 6-4v14l-6-4',
  table: 'M3 4h18v16H3V4Zm0 6h18M9 10v10M15 10v10',
  trash: 'M4 7h16M9 7V4h6v3M6 7l1 13h10l1-13M10 10v7M14 10v7',
  edit: 'm15 5 4 4M4 20l4-1L20 7a2.8 2.8 0 0 0-4-4L4 15v5Z',
  pin: 'M8 3h8M8 3v6l-3 3v3h14v-3l-3-3V3M12 15v7',
  unpin: 'M8 3h8M8 3v6l-3 3v3h14v-3l-3-3V3M12 15v7M3 3l18 18',
  more: 'M5 12h.01M12 12h.01M19 12h.01',
  sun: 'M12 8a4 4 0 1 0 0 8 4 4 0 0 0 0-8ZM12 2v2M12 20v2M2 12h2M20 12h2M5 5l1.5 1.5M17.5 17.5 19 19M5 19l1.5-1.5M17.5 6.5 19 5',
  moon: 'M20.8 13A9 9 0 0 1 11 3a9 9 0 1 0 9.8 10Z',
  close: 'm6 6 12 12M6 18 18 6',
  stop: 'M8 6h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H8a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2Z',
  download: 'M12 3v12m-5-5 5 5 5-5M5 16v5h14v-5',
  refresh: 'M20 7v5h-5M4 17v-5h5M5.4 7a8 8 0 0 1 13-2L20 7M4 17l1.6 2a8 8 0 0 0 13-2',
  check: 'm5 12 4 4L19 6',
  info: 'M12 8h.01M12 11v6M22 12a10 10 0 1 1-20 0 10 10 0 0 1 20 0Z',
};
</script>

<template>
  <svg class="icon" :width="size" :height="size" viewBox="0 0 24 24" fill="none" stroke="currentColor" :stroke-width="name === 'more' ? 3 : 1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true" focusable="false"><path :d="paths[name] || paths.plus" :fill="name === 'stop' ? 'currentColor' : 'none'" /></svg>
</template>
