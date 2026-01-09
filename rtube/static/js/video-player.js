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
            seekStep: 10,
            customKeys: {
                theaterMode: {
                    key: function(event) {
                        return event.which === 84; // 't' key
                    },
                    handler: function(player, options, event) {
                        toggleTheaterMode();
                    }
                }
            }
        }
    }
});

player.test();
player.hlsQualitySelector({ displayCurrentQuality: true });

// Theater mode functionality
function toggleTheaterMode() {
    var body = document.body;
    var isTheater = body.classList.toggle('theater-mode');

    // Update button state
    var btn = document.querySelector('.vjs-theater-button');
    if (btn) {
        btn.classList.toggle('vjs-theater-active', isTheater);
        btn.setAttribute('title', isTheater ? 'Exit Theater Mode (t)' : 'Theater Mode (t)');
    }

    // Save preference to localStorage
    localStorage.setItem('rtube-theater-mode', isTheater ? 'true' : 'false');

    // Trigger video.js resize to adjust to new dimensions
    setTimeout(function() {
        player.trigger('resize');
    }, 100);
}

// Initialize theater mode from saved preference
function initTheaterMode() {
    var savedPreference = localStorage.getItem('rtube-theater-mode');
    if (savedPreference === 'true') {
        document.body.classList.add('theater-mode');
        var btn = document.querySelector('.vjs-theater-button');
        if (btn) {
            btn.classList.add('vjs-theater-active');
            btn.setAttribute('title', 'Exit Theater Mode (t)');
        }
    }
}

// Create Theater Mode Button component
var Button = videojs.getComponent('Button');
var TheaterButton = videojs.extend(Button, {
    constructor: function(player, options) {
        Button.call(this, player, options);
        this.controlText('Theater Mode (t)');
        this.addClass('vjs-theater-button');

        // Set initial state based on saved preference
        if (localStorage.getItem('rtube-theater-mode') === 'true') {
            this.addClass('vjs-theater-active');
            this.controlText('Exit Theater Mode (t)');
        }
    },
    handleClick: function() {
        toggleTheaterMode();
    },
    buildCSSClass: function() {
        return 'vjs-theater-button ' + Button.prototype.buildCSSClass.call(this);
    }
});

// Register the component
videojs.registerComponent('TheaterButton', TheaterButton);

// Add the button to the control bar
player.ready(function() {
    player.getChild('controlBar').addChild('TheaterButton', {}, 11);
    initTheaterMode();
});

// Watch history tracking
var watchHistoryEnabled = typeof videoShortId !== 'undefined' && videoShortId;
var lastSavedPosition = 0;
var saveInterval = null;

function saveWatchProgress() {
    if (!watchHistoryEnabled) return;

    var currentPosition = player.currentTime();
    var duration = player.duration();

    // Only save if position changed significantly (more than 5 seconds)
    if (Math.abs(currentPosition - lastSavedPosition) < 5) return;

    lastSavedPosition = currentPosition;

    fetch('/watch/progress?v=' + videoShortId, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({
            position: currentPosition,
            duration: duration || null
        })
    }).catch(function(err) {
        console.log('Failed to save watch progress:', err);
    });
}

function loadWatchProgress(callback) {
    if (!watchHistoryEnabled) {
        callback(0);
        return;
    }

    fetch('/watch/progress?v=' + videoShortId)
        .then(function(response) {
            if (response.ok) return response.json();
            return { position: 0 };
        })
        .then(function(data) {
            callback(data.position || 0);
        })
        .catch(function() {
            callback(0);
        });
}

// Seek to start time if specified (e.g., ?t=90 in URL) or resume from history
player.ready(function() {
    player.one('loadedmetadata', function() {
        if (typeof startTime !== 'undefined' && startTime > 0) {
            // URL parameter takes priority
            player.currentTime(startTime);
            lastSavedPosition = startTime;
        } else {
            // Try to resume from watch history
            loadWatchProgress(function(savedPosition) {
                if (savedPosition > 10) {
                    // Only resume if saved position is more than 10 seconds
                    // and not near the end (90% of duration)
                    var duration = player.duration();
                    if (!duration || savedPosition < duration * 0.9) {
                        player.currentTime(savedPosition);
                        lastSavedPosition = savedPosition;
                    }
                }
            });
        }
    });

    // Save progress periodically while playing (every 10 seconds)
    player.on('play', function() {
        if (watchHistoryEnabled && !saveInterval) {
            saveInterval = setInterval(saveWatchProgress, 10000);
        }
    });

    player.on('pause', function() {
        // Save immediately when paused
        saveWatchProgress();
    });

    player.on('ended', function() {
        // Save final position when video ends
        saveWatchProgress();
        if (saveInterval) {
            clearInterval(saveInterval);
            saveInterval = null;
        }
    });

    // Save when user leaves the page
    window.addEventListener('beforeunload', function() {
        if (watchHistoryEnabled) {
            // Use sendBeacon for reliable save on page unload
            var data = JSON.stringify({
                position: player.currentTime(),
                duration: player.duration() || null
            });
            navigator.sendBeacon('/watch/progress?v=' + videoShortId, new Blob([data], { type: 'application/json' }));
        }
    });
});

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
