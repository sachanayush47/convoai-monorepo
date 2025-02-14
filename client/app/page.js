"use client";
import React from "react";

const AudioStreamingComponent = () => {
    const [isStreaming, setIsStreaming] = React.useState(false);
    const [connectionStatus, setConnectionStatus] = React.useState("disconnected");
    const websocketRef = React.useRef(null);
    const mediaRecorderRef = React.useRef(null);
    const audioContextRef = React.useRef(null);
    const audioQueueRef = React.useRef([]);
    const isPlayingRef = React.useRef(false);
    const agentId = "e4adba25-65d0-4fee-9d00-f06671babcf1";

    // Initialize audio context
    React.useEffect(() => {
        audioContextRef.current = new (window.AudioContext || window.webkitAudioContext)();
        return () => {
            if (audioContextRef.current) {
                audioContextRef.current.close();
            }
        };
    }, []);

    // Play audio chunks sequentially. Queue is used to handle multiple chunks and prevent overlapping.
    const playNextInQueue = async () => {
        if (audioQueueRef.current.length === 0) {
            isPlayingRef.current = false;
            return;
        }

        isPlayingRef.current = true;
        const audioData = audioQueueRef.current.shift();

        try {
            const arrayBuffer = await audioData.arrayBuffer();
            const audioBuffer = await audioContextRef.current.decodeAudioData(arrayBuffer);

            const source = audioContextRef.current.createBufferSource();
            source.buffer = audioBuffer;
            source.connect(audioContextRef.current.destination);

            source.onended = () => {
                playNextInQueue();
            };

            source.start(0);
        } catch (error) {
            console.error("ERROR PLAYING AUDIO:", error);
            playNextInQueue();
        }
    };

    const toggleStreaming = async () => {
        if (isStreaming) {
            if (mediaRecorderRef.current) {
                mediaRecorderRef.current.stop();
            }
            if (websocketRef.current) {
                websocketRef.current.close();
            }
            setIsStreaming(false);
            setConnectionStatus("disconnected");

            // Clear audio queue when stopping
            audioQueueRef.current = [];
        } else {
            try {
                setConnectionStatus("connecting");

                const ws = new WebSocket(`ws://localhost:8000/ws/chat/${agentId}`);

                await new Promise((resolve, reject) => {
                    ws.onopen = resolve;
                    ws.onerror = reject;
                });

                websocketRef.current = ws;
                setConnectionStatus("connected");

                const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
                const mediaRecorder = new MediaRecorder(stream);

                mediaRecorder.ondataavailable = (event) => {
                    if (event.data.size > 0 && ws.readyState === WebSocket.OPEN) {
                        ws.send(event.data);
                    }
                };

                mediaRecorder.onstop = () => {
                    stream.getTracks().forEach((track) => track.stop());
                };

                ws.onclose = () => {
                    setConnectionStatus("disconnected");
                    setIsStreaming(false);
                    if (mediaRecorderRef.current) {
                        mediaRecorderRef.current.stop();
                    }
                };

                ws.onmessage = async (event) => {
                    // Handle incoming audio data
                    if (event.data instanceof Blob) {
                        audioQueueRef.current.push(event.data);
                        if (!isPlayingRef.current) {
                            playNextInQueue();
                        }
                    }
                };

                mediaRecorderRef.current = mediaRecorder;
                mediaRecorder.start(100);
                setIsStreaming(true);
            } catch (error) {
                console.error("Error starting stream:", error);
                setConnectionStatus("error");
            }
        }
    };

    return (
        <div className="pt-64">
            <div className="w-full max-w-md mx-auto bg-white shadow-lg rounded-lg p-6">
                <div className="flex flex-col items-center gap-4">
                    <div className="text-sm">
                        {connectionStatus === "connected" && (
                            <span className="text-green-600">Connected & Streaming</span>
                        )}
                        {connectionStatus === "connecting" && <span className="text-yellow-600">Connecting...</span>}
                        {connectionStatus === "disconnected" && <span className="text-gray-600">Ready to Connect</span>}
                        {connectionStatus === "error" && <span className="text-red-600">Connection Error</span>}
                    </div>

                    <button
                        onClick={toggleStreaming}
                        className={`
                            w-16 h-16 rounded-full flex items-center justify-center
                            ${
                                connectionStatus === "error"
                                    ? "bg-red-500"
                                    : isStreaming
                                    ? "bg-red-500 hover:bg-red-600"
                                    : "bg-blue-500 hover:bg-blue-600"
                            }
                            transition-colors duration-200
                        `}
                    >
                        <div
                            className={`
                                ${isStreaming ? "w-6 h-6 bg-white rounded" : "w-6 h-6 bg-white rounded-full"}
                            `}
                        ></div>
                    </button>

                    <div className="text-sm text-gray-600">
                        {isStreaming ? "Click to stop" : "Click to start streaming"}
                    </div>
                </div>
            </div>
        </div>
    );
};

export default AudioStreamingComponent;
