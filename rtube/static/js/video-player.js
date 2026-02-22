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

        }
    }
});

player.test();
player.hlsQualitySelector({ displayCurrentQuality: true });

// Add the button to the control bar
player.ready(function () {
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
    }).catch(function (err) {
        console.log('Failed to save watch progress:', err);
    });
}

function loadWatchProgress(callback) {
    if (!watchHistoryEnabled) {
        callback(0);
        return;
    }

    fetch('/watch/progress?v=' + videoShortId)
        .then(function (response) {
            if (response.ok) return response.json();
            return { position: 0 };
        })
        .then(function (data) {
            callback(data.position || 0);
        })
        .catch(function () {
            callback(0);
        });
}

// Seek to start time if specified (e.g., ?t=90 in URL) or resume from history
player.ready(function () {
    player.one('loadedmetadata', function () {
        if (typeof startTime !== 'undefined' && startTime > 0) {
            // URL parameter takes priority
            player.currentTime(startTime);
            lastSavedPosition = startTime;
        } else {
            // Try to resume from watch history
            loadWatchProgress(function (savedPosition) {
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
    player.on('play', function () {
        if (watchHistoryEnabled && !saveInterval) {
            saveInterval = setInterval(saveWatchProgress, 10000);
        }
    });

    player.on('pause', function () {
        // Save immediately when paused
        saveWatchProgress();
    });

    player.on('ended', function () {
        // Save final position when video ends
        saveWatchProgress();
        if (saveInterval) {
            clearInterval(saveInterval);
            saveInterval = null;
        }
    });

    // Save when user leaves the page
    window.addEventListener('beforeunload', function () {
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
    markerTip: {
        display: true
    },
    breakOverlay: {
        display: false,
        displayTime: 3,
        style: {
            'width': '100%',
            'height': '20%',
            'background-color': 'rgba(0,0,0,0.7)',
            'color': 'white',
            'font-size': '17px'
        }
    },
    markers: mymarkers
});
