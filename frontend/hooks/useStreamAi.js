import { useState, useRef, useCallback, useEffect } from 'react';
import debounce from 'lodash/debounce';
import { normalizeMarkdown } from '../lib/markdown';
import { STREAM_MARKERS } from '../lib/constants';

export function useStreamAi({ onComplete, onError } = {}) {
  const [content, setContent] = useState({ thinking: '', report: '' });
  const [isGenerating, setIsGenerating] = useState(false);
  const abortControllerRef = useRef(null);
  
  // Use refs for callbacks to avoid dependency cycles causing infinite loops
  const onCompleteRef = useRef(onComplete);
  const onErrorRef = useRef(onError);

  useEffect(() => {
    onCompleteRef.current = onComplete;
    onErrorRef.current = onError;
  }, [onComplete, onError]);
  
  // Debounced updater to prevent excessive re-renders
  const debouncedUpdate = useRef(
    debounce((newContent) => {
      setContent(newContent);
    }, 120)
  ).current;

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      debouncedUpdate.cancel();
      if (abortControllerRef.current) {
        abortControllerRef.current.abort();
      }
    };
  }, [debouncedUpdate]);

  const generate = useCallback(async (apiCallFactory) => {
    // Cancel any ongoing request
    if (abortControllerRef.current) {
        abortControllerRef.current.abort();
    }
    const abortController = new AbortController();
    abortControllerRef.current = abortController;

    setIsGenerating(true);
    // Initial state
    setContent({ thinking: '正在建立神经网络连接...', report: '' });
    
    try {
        const response = await apiCallFactory(abortController.signal);
        
        if (!response.body) {
             // Handle cases where response might be JSON (error or direct result)
             // But for this hook we expect a stream.
             setIsGenerating(false);
             return; 
        }

        const reader = response.body.getReader();
        const decoder = new TextDecoder();
        let fullResponse = '';
        let isFirstChunk = true;

        while (true) {
            const { value, done } = await reader.read();
            if (done) break;
            
            const chunk = decoder.decode(value, { stream: true });
            fullResponse += chunk;
            
            // --- Parse Logic ---
            // 1. Remove Function Calls
            const cleanedContent = fullResponse.replace(
                STREAM_MARKERS.FUNCTION_CALL_REGEX,
                ''
            );

            let currentThinking = '';
            let currentReport = '';

            // 2. Split Thinking and Report
            if (cleanedContent.includes(STREAM_MARKERS.REPORT_START)) {
                const parts = cleanedContent.split(STREAM_MARKERS.REPORT_START, 2);
                currentThinking = parts[0].replace(STREAM_MARKERS.THINK_END, '');
                currentReport = parts[1];
            } else if (cleanedContent.includes(STREAM_MARKERS.THINK_END)) {
                currentThinking = cleanedContent.replace(STREAM_MARKERS.THINK_END, '');
            } else {
                currentThinking = cleanedContent;
            }

            const newContent = {
                thinking: normalizeMarkdown(currentThinking),
                report: normalizeMarkdown(currentReport),
            };

            // 3. Update State
            if (isFirstChunk) {
                setContent(newContent);
                isFirstChunk = false;
            } else {
                debouncedUpdate(newContent);
            }
        }
        
        debouncedUpdate.flush();
        
        // Final completion callback
        if (onCompleteRef.current) {
            const finalCleaned = fullResponse.replace(STREAM_MARKERS.FUNCTION_CALL_REGEX, '');
            const finalParts = finalCleaned.split(STREAM_MARKERS.REPORT_START, 2);
            if (finalParts.length > 1) {
                onCompleteRef.current(normalizeMarkdown(finalParts[1]).trim());
            } else {
                // If only thinking, completion might be just thinking
                onCompleteRef.current(normalizeMarkdown(finalCleaned).trim());
            }
        }

    } catch (e) {
        if (e.name === 'AbortError') {
            console.log('Stream aborted');
        } else {
            console.error("Stream generation error:", e);
            if (onErrorRef.current) onErrorRef.current(e.message || String(e));
        }
    } finally {
        if (abortControllerRef.current === abortController) {
             setIsGenerating(false);
             abortControllerRef.current = null;
        }
    }
  }, [debouncedUpdate]); // Removed onComplete, onError from dependencies

  const reset = useCallback(() => {
      if (abortControllerRef.current) abortControllerRef.current.abort();
      setContent({ thinking: '', report: '' });
      setIsGenerating(false);
  }, []);

  return {
    content,
    isGenerating,
    generate,
    reset
  };
}
