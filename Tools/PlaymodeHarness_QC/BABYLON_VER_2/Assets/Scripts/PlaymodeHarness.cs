using System;
using UnityEngine;
#if UNITY_EDITOR
using UnityEditor;
using UnityEditor.SceneManagement;
#endif

namespace Babylon.CI
{
    /// <summary>
    /// Spins a deterministic Play Mode loop so CI runs can prove that runtime ticks occurred.
    /// </summary>
    internal static class PlaymodeHarness
    {
        private const string ExecutionModeEnv = "BABYLON_CI_EXECUTION_MODE";
        private const string RequiredValue = "playmode_required";
        private const int TargetFrameCount = 30;

#if UNITY_EDITOR
        public static void RunFromCommandLine()
        {
            if (!IsPlaymodeRequired())
            {
                Debug.Log("[PLAYMODE] Harness invoked without playmode_required; exiting.");
                EditorApplication.Exit(0);
                return;
            }

            EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
            EditorApplication.isPlaying = true;
        }
#endif

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
        private static void InitializeTicker()
        {
            if (!ShouldArmTicker())
            {
                return;
            }

            Debug.Log("[PLAYMODE] entered");
            var tickerHost = new GameObject("PlaymodeHarnessTicker")
            {
                hideFlags = HideFlags.HideAndDontSave,
            };
            UnityEngine.Object.DontDestroyOnLoad(tickerHost);
            tickerHost.AddComponent<PlaymodeHarnessTicker>();
        }

        private static bool ShouldArmTicker()
        {
            if (!Application.isPlaying)
            {
                return false;
            }

#if UNITY_EDITOR
            if (!EditorApplication.isPlaying)
            {
                return false;
            }
#endif

            return IsPlaymodeRequired();
        }

        private sealed class PlaymodeHarnessTicker : MonoBehaviour
        {
            private int _frames;

            private void Update()
            {
                _frames++;
                if (_frames < TargetFrameCount)
                {
                    return;
                }

                Debug.Log($"[PLAYMODE] tick_ok frames={_frames}");
#if UNITY_EDITOR
                EditorApplication.ExitPlaymode();
                EditorApplication.Exit(0);
#else
                Application.Quit(0);
#endif
            }
        }

        private static bool IsPlaymodeRequired()
        {
            var value = System.Environment.GetEnvironmentVariable(ExecutionModeEnv);
            if (string.IsNullOrWhiteSpace(value))
            {
                return false;
            }

            return string.Equals(value.Trim(), RequiredValue, StringComparison.OrdinalIgnoreCase);
        }
    }
}
