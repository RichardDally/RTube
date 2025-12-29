var player = videojs("RPlayer", {
    autoplay: false,
    controls: true,
    responsive: true,
    loop: false,
    fluid: false,
    playbackRates: [0.25, 0.5, 1, 1.5, 2],
    plugins: {
        hotkeys: {
            enableModifiersForNumbers: false,
            seekStep: 10
        }
    }
});

player.test();
player.hlsQualitySelector({ displayCurrentQuality: true });

// Seek to start time if specified (e.g., ?t=90 in URL)
if (typeof startTime !== 'undefined' && startTime > 0) {
    player.ready(function() {
        player.one('loadedmetadata', function() {
            player.currentTime(startTime);
        });
    });
}

player.markers({
   markerTip:{
      display: true
   },
   breakOverlay:{
      display: true,
      displayTime: 3,
      style:{
         'width':'100%',
         'height': '20%',
         'background-color': 'rgba(0,0,0,0.7)',
         'color': 'white',
         'font-size': '17px'
      }
   },
   markers: mymarkers
});
