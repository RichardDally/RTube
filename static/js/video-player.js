var player = videojs("RPlayer", {
    autoplay: "muted",
    controls: true,
    responsive: true,
    loop: false,
    fluid: true,
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
