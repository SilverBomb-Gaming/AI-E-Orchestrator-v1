using System;
using System.Collections;
using System.Collections.Generic;
using System.Globalization;
using System.IO;
using System.Linq;
using System.Reflection;
using Babylon.Characters;
using Babylon.Systems;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.SceneManagement;
#if UNITY_RENDER_PIPELINE_URP
using UnityEngine.Rendering.Universal;
#endif

namespace Babylon.Gameplay.Viewmodel
{
    /// <summary>
    /// Emits deterministic viewmodel diagnostics during CI runs so the audit script has signal to parse.
    /// </summary>
    internal static class ViewmodelAuditProbe
    {
        private const string ExecutionModeEnvVar = "BABYLON_CI_EXECUTION_MODE";
        private const string PlaymodeRequiredValue = "playmode_required";
        private static bool _hasRun;
        private static bool _pipelineLogged;
        private static readonly CultureInfo Invariant = CultureInfo.InvariantCulture;

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.BeforeSplashScreen)]
        private static void RunBeforeSplash()
        {
            RunInternal("RuntimeBeforeSplash");
        }

#if UNITY_EDITOR
        [UnityEditor.InitializeOnLoadMethod]
        private static void RunOnEditorReload()
        {
            RunInternal("EditorInitializeOnLoad");
        }
#endif

        private static void RunInternal(string reason)
        {
            if (_hasRun)
            {
                return;
            }

            if (!Application.isBatchMode)
            {
                return;
            }

            if (!IsPlaymodeProbeEnabled())
            {
                Debug.Log("[GAMEPLAY][Probe] Skipped (playmode not requested).");
                return;
            }

            _hasRun = true;

            GameplayViewmodelProbe.Schedule(reason);

            try
            {
                Execute(reason);
            }
            catch (Exception ex)
            {
                Debug.LogWarning($"[ViewmodelAudit] Probe aborted: {ex.Message}");
            }
        }

        private static bool IsPlaymodeProbeEnabled()
        {
            var value = System.Environment.GetEnvironmentVariable(ExecutionModeEnvVar);
            if (string.IsNullOrWhiteSpace(value))
            {
                return false;
            }

            return string.Equals(value.Trim(), PlaymodeRequiredValue, StringComparison.OrdinalIgnoreCase);
        }

        private static void Execute(string reason)
        {
            var weapons = CollectWeapons(out var syntheticWeapons);
            if (weapons == null || weapons.Count == 0)
            {
                Debug.LogWarning("[ViewmodelAudit] No WeaponData assets were discovered under Resources/Weapons.");
                return;
            }

            Debug.Log($"[ViewmodelAudit] Probe executing ({reason}).");

            var root = new GameObject("ViewmodelAuditRoot")
            {
                hideFlags = HideFlags.HideAndDontSave,
            };

            Camera auditCamera = null;

            try
            {
                auditCamera = CreateAuditCamera(root.transform);
                LogPipelineDiagnostics(auditCamera);

                foreach (var weapon in weapons.OrderBy(w => w != null ? w.weaponName : string.Empty))
                {
                    AuditWeapon(weapon, root.transform, auditCamera);
                }
            }
            finally
            {
                if (auditCamera != null)
                {
                    UnityEngine.Object.DestroyImmediate(auditCamera.gameObject);
                }

                UnityEngine.Object.DestroyImmediate(root);
#if UNITY_EDITOR
                DestroySyntheticWeapons(syntheticWeapons);
#endif
            }
        }

        private static IReadOnlyList<WeaponData> CollectWeapons(out List<WeaponData> syntheticWeapons)
        {
            syntheticWeapons = null;
            var resources = Resources.LoadAll<WeaponData>("Weapons");
            if (resources != null && resources.Length > 0)
            {
                return resources.Where(item => item != null).ToArray();
            }

#if UNITY_EDITOR
            var clones = BuildSyntheticWeapons();
            if (clones.Count > 0)
            {
                syntheticWeapons = clones;
                return clones;
            }
#endif

            return Array.Empty<WeaponData>();
        }

#if UNITY_EDITOR
        private static List<WeaponData> BuildSyntheticWeapons()
        {
            var weaponsDirectory = Path.Combine(Application.dataPath, "Resources", "Weapons");
            if (!Directory.Exists(weaponsDirectory))
            {
                return new List<WeaponData>();
            }

            var names = Directory.EnumerateFiles(weaponsDirectory, "*.asset", SearchOption.TopDirectoryOnly)
                .Select(path => Path.GetFileNameWithoutExtension(path))
                .Where(name => !string.IsNullOrWhiteSpace(name))
                .Distinct(StringComparer.OrdinalIgnoreCase)
                .OrderBy(name => name, StringComparer.OrdinalIgnoreCase)
                .ToList();

            var clones = new List<WeaponData>(names.Count);
            foreach (var name in names)
            {
                clones.Add(ViewmodelConfigurator.CreateProfileClone(name));
            }

            if (clones.Count > 0)
            {
                Debug.Log($"[ViewmodelAudit] Synthesized {clones.Count} WeaponData entries from Resources/Weapons.");
            }

            return clones;
        }

        private static void DestroySyntheticWeapons(List<WeaponData> syntheticWeapons)
        {
            if (syntheticWeapons == null || syntheticWeapons.Count == 0)
            {
                return;
            }

            foreach (var weapon in syntheticWeapons)
            {
                if (weapon != null)
                {
                    UnityEngine.Object.DestroyImmediate(weapon);
                }
            }
        }
#endif

        private static Camera CreateAuditCamera(Transform parent)
        {
            var go = new GameObject("ViewmodelAuditCamera")
            {
                hideFlags = HideFlags.HideAndDontSave,
            };

            if (parent != null)
            {
                go.transform.SetParent(parent, false);
            }

            go.transform.localPosition = new Vector3(0f, 0f, -0.5f);
            go.transform.localRotation = Quaternion.identity;

            var camera = go.AddComponent<Camera>();
            camera.enabled = true;
            camera.clearFlags = CameraClearFlags.SolidColor;
            camera.backgroundColor = Color.black;
            camera.nearClipPlane = 0.01f;
            camera.farClipPlane = 25f;
            camera.fieldOfView = 60f;
            camera.orthographic = false;
            camera.cullingMask = ~0;
            camera.depth = -100f;

            return camera;
        }

        private static void EnsureCameraSeesLayer(Camera camera, int layerIndex)
        {
            if (camera == null)
            {
                return;
            }

            if (layerIndex < 0 || layerIndex > 31)
            {
                return;
            }

            camera.cullingMask |= 1 << layerIndex;
        }

        private static void PositionAuditCamera(Camera camera, Transform target)
        {
            if (camera == null || target == null)
            {
                return;
            }

            var forward = target.forward.sqrMagnitude > 0.0001f ? target.forward.normalized : Vector3.forward;
            camera.transform.position = target.position - forward * 0.5f;
            camera.transform.rotation = target.rotation;
        }

        private static void AuditWeapon(WeaponData weapon, Transform parent, Camera auditCamera)
        {
            var weaponName = weapon != null && !string.IsNullOrEmpty(weapon.weaponName)
                ? weapon.weaponName
                : "<unnamed>";

            GameObject instance = null;
            string prefabName = "<null>";
            if (weapon != null && weapon.weaponPrefab != null)
            {
                prefabName = weapon.weaponPrefab.name;
                instance = UnityEngine.Object.Instantiate(weapon.weaponPrefab, parent);
                instance.name = $"{weaponName}_AuditInstance";
                instance.hideFlags = HideFlags.HideAndDontSave;
            }

            var parentName = instance != null && instance.transform.parent != null
                ? instance.transform.parent.name
                : "<null>";
            var layerIndex = instance != null ? instance.layer : 0;
            var layerName = LayerMask.LayerToName(layerIndex);
            if (string.IsNullOrEmpty(layerName))
            {
                layerName = "Default";
            }

            var renderers = instance != null
                ? instance.GetComponentsInChildren<Renderer>(true)
                : Array.Empty<Renderer>();

            Debug.Log(
                $"[WEAPON][Audit] weapon={weaponName}, prefab={prefabName}, instance={(instance != null ? instance.name : "<null>")}, " +
                $"parent={parentName}, active={(instance != null && instance.activeInHierarchy)}, layer={layerName}({layerIndex}), holder=ViewmodelAudit, renderers={renderers.Length}");

            if (renderers.Length == 0 && instance != null)
            {
                Debug.Log($"[WEAPON][Audit] No Renderer components found under {instance.name}.");
            }

            var rendererDiagnostics = BuildRendererDiagnostics(renderers);
            foreach (var diagnostic in rendererDiagnostics)
            {
                Debug.Log(
                    $"[WEAPON][Renderer] weapon={weaponName}, path={diagnostic.Path}, name={diagnostic.Name}, type={diagnostic.RendererType}, " +
                    $"enabled={diagnostic.RendererEnabled}, goActive={diagnostic.GameObjectActive}, layer={diagnostic.LayerName}({diagnostic.LayerIndex}), " +
                    $"sortingLayer={diagnostic.SortingLayerName}({diagnostic.SortingLayerId}), sortingOrder={diagnostic.SortingOrder}, shadowCasting={diagnostic.ShadowCastingMode}, " +
                    $"receiveShadows={diagnostic.ReceiveShadows}, boundsCenter={FormatVector(diagnostic.BoundsCenter)}, boundsExtents={FormatVector(diagnostic.BoundsExtents)}, " +
                    $"materialCount={diagnostic.Materials.Count}");

                foreach (var material in diagnostic.Materials)
                {
                    Debug.Log(
                        $"[WEAPON][Material] weapon={weaponName}, renderer={diagnostic.Name}, material={material.Name}, shader={material.ShaderName}, " +
                        $"renderQueue={material.RenderQueue}, hasColor={material.HasColor}, colorAlpha={FormatFloat(material.ColorAlpha)}, surface={FormatFloat(material.Surface)}, " +
                        $"alphaClip={FormatFloat(material.AlphaClip)}, cutoff={FormatFloat(material.Cutoff)}, zwrite={FormatFloat(material.ZWrite)}");
                }
            }

            var rendererLayers = rendererDiagnostics
                .Select(diagnostic => diagnostic.LayerIndex)
                .Where(layer => layer >= 0 && layer <= 31)
                .Distinct()
                .OrderBy(layer => layer)
                .ToList();

            var anyRendererDisabled = rendererDiagnostics.Any(diagnostic => !diagnostic.RendererEnabled || !diagnostic.GameObjectActive);
            var anyMaterialMissing = rendererDiagnostics.Any(diagnostic => diagnostic.Materials.Count == 0 || diagnostic.Materials.Any(material => material.IsMissing));
            var anyAlphaZero = rendererDiagnostics.Any(diagnostic => diagnostic.Materials.Any(material => material.AlphaZero));

            Debug.Log(
                $"[WEAPON][Renderers] weapon={weaponName}, count={rendererDiagnostics.Count}, uniqueLayers={FormatLayerSet(rendererLayers)}, " +
                $"anyDisabled={anyRendererDisabled}, anyMaterialMissing={anyMaterialMissing}, anyAlphaZero={anyAlphaZero}");

            var layerCamera = Camera.main != null ? Camera.main : auditCamera;
            var cameraIncludesRoot = LayerIncluded(layerCamera, layerIndex);
            var rendererLayersIncluded = AreAllLayersIncluded(layerCamera, rendererLayers);
            Debug.Log(
                $"[WEAPON][Layers] weapon={weaponName}, rootLayer={layerName}({layerIndex}), cameraIncludesRoot={cameraIncludesRoot}, " +
                $"rendererLayersIncluded={rendererLayersIncluded}");

            if (weapon != null)
            {
                Debug.Log(
                    $"[WEAPON][Offsets] weapon={weaponName}, fpPos={weapon.fpLocalPosition}, fpEuler={weapon.fpLocalEuler}, fpScale={weapon.fpLocalScale}");
            }

            if (instance == null)
            {
                LogHeuristics(weaponName, false, false, Array.Empty<CameraDiagnostic>());
                return;
            }

            var instanceTransform = instance.transform;
            EnsureCameraSeesLayer(auditCamera, layerIndex);
            PositionAuditCamera(auditCamera, instanceTransform);
            var mainCamera = Camera.main;
            var referenceCamera = mainCamera != null ? mainCamera : auditCamera;
            LogTransform(weaponName, instanceTransform, referenceCamera);
            var cameraDiagnostics = LogCameraDiagnostics(weaponName, instanceTransform, layerIndex, layerName, rendererLayers, mainCamera, auditCamera);
            LogHeuristics(weaponName, true, instance.activeInHierarchy, cameraDiagnostics);

            UnityEngine.Object.DestroyImmediate(instance);
        }

        private sealed class CameraDiagnostic
        {
            public string Name { get; set; }
            public bool Active { get; set; }
            public bool IncludesLayer { get; set; }
            public bool IncludesRendererLayers { get; set; }
            public bool BehindCamera { get; set; }
            public bool IsMain { get; set; }
            public bool IsViewmodel { get; set; }
            public int CullingMask { get; set; }
            public string CullingLayers { get; set; }
            public float NearClip { get; set; }
            public float FieldOfView { get; set; }
            public float RelativeZ { get; set; }
            public float Distance { get; set; }
            public string RenderType { get; set; }
        }

        private sealed class RendererDiagnostic
        {
            public string Name { get; set; }
            public string Path { get; set; }
            public string RendererType { get; set; }
            public bool RendererEnabled { get; set; }
            public bool GameObjectActive { get; set; }
            public string LayerName { get; set; }
            public int LayerIndex { get; set; }
            public string SortingLayerName { get; set; }
            public int SortingLayerId { get; set; }
            public int SortingOrder { get; set; }
            public ShadowCastingMode ShadowCastingMode { get; set; }
            public bool ReceiveShadows { get; set; }
            public Vector3 BoundsCenter { get; set; }
            public Vector3 BoundsExtents { get; set; }
            public List<RendererMaterialDiagnostic> Materials { get; } = new List<RendererMaterialDiagnostic>();
        }

        private sealed class RendererMaterialDiagnostic
        {
            public string Name { get; set; }
            public string ShaderName { get; set; }
            public int RenderQueue { get; set; }
            public bool HasColor { get; set; }
            public float? ColorAlpha { get; set; }
            public float? Surface { get; set; }
            public float? AlphaClip { get; set; }
            public float? Cutoff { get; set; }
            public float? ZWrite { get; set; }
            public bool IsMissing => string.Equals(Name, "<null>", StringComparison.OrdinalIgnoreCase);
            public bool AlphaZero => ColorAlpha.HasValue && ColorAlpha.Value <= 0.001f;
        }

        private static class GameplayViewmodelProbe
        {
            private static bool _scheduled;
            private static bool _completed;
            private static bool _quitRequested;
            private static bool _allowQuit;

            static GameplayViewmodelProbe()
            {
                Application.wantsToQuit += OnApplicationWantsToQuit;
#if UNITY_EDITOR
                UnityEditor.EditorApplication.wantsToQuit += OnEditorWantsToQuit;
#endif
            }

            public static void Schedule(string reason)
            {
                if (_scheduled || !Application.isBatchMode)
                {
                    return;
                }

                _scheduled = true;

                var go = new GameObject("GameplayViewmodelProbeHost")
                {
                    hideFlags = HideFlags.HideAndDontSave,
                };

                var host = go.AddComponent<GameplayViewmodelProbeHost>();
                host.Configure(reason);
                host.Begin();
                Debug.Log($"[GAMEPLAY][Probe] Scheduled gameplay probe host reason={reason}");
            }

            internal static void NotifyCompleted()
            {
                if (_completed)
                {
                    return;
                }

                _completed = true;
                _allowQuit = true;

                if (_quitRequested)
                {
                    Debug.Log("[GAMEPLAY][Probe] Gameplay probe complete, allowing application quit.");
                }
                else
                {
                    Debug.Log("[GAMEPLAY][Probe] Gameplay probe complete, requesting application quit.");
                }

                if (!Application.isBatchMode)
                {
                    return;
                }

#if UNITY_EDITOR
                UnityEditor.EditorApplication.Exit(0);
#else
                Application.Quit();
#endif
            }

            private static bool OnApplicationWantsToQuit()
            {
                return HandleQuitRequest("Application");
            }

#if UNITY_EDITOR
            private static bool OnEditorWantsToQuit()
            {
                return HandleQuitRequest("Editor");
            }
#endif

            private static bool HandleQuitRequest(string source)
            {
                if (_allowQuit || _completed || !Application.isBatchMode)
                {
                    return true;
                }

                if (!_scheduled)
                {
                    Schedule($"{source}WantsToQuit");
                }

                _quitRequested = true;
                Debug.Log($"[GAMEPLAY][Probe] Blocking {source} quit until gameplay probe finalizes.");
                return false;
            }
        }

        [ExecuteInEditMode]
        private sealed class GameplayViewmodelProbeHost : MonoBehaviour
        {
            private const float SceneLoadTimeoutSeconds = 10f;
            private const float CameraWaitTimeoutSeconds = 5f;
            private const float WeaponManagerWaitTimeoutSeconds = 5f;
            private const float ViewmodelWaitTimeoutSeconds = 5f;
            private const float EquipSettleSeconds = 0.25f;

            private static readonly FieldInfo CurrentWeaponObjectField = typeof(WeaponManager).GetField("currentWeaponObject", BindingFlags.Instance | BindingFlags.NonPublic);
            private static readonly MethodInfo SwitchWeaponMethod = typeof(WeaponManager).GetMethod("SwitchWeapon", BindingFlags.Instance | BindingFlags.NonPublic);
            private static readonly string[] PreferredGameplaySceneNames = new[]
            {
                "Babylon FPS game ver 001",
                "Babylon FPS game ver 002",
                "Babylon FPS game ver 003",
                "Babylon FPS game ver 004",
                "Babylon FPS game",
                "QA_Test",
            };

            private string _reason = "<unspecified>";
            private bool _reportWritten;
            private bool _started;
            private readonly List<Camera> _cameraCache = new List<Camera>(8);
#if UNITY_EDITOR
            private Scene _originalScene;
            private Scene _loadedScene;
            private bool _restoreScene;
#endif

            internal void Configure(string reason)
            {
                if (!string.IsNullOrEmpty(reason))
                {
                    _reason = reason;
                }
            }

            private void Awake()
            {
            }

            private void Start()
            {
                Debug.Log("[GAMEPLAY][Probe] Host starting");
                Begin();
            }

            private void OnDestroy()
            {
                Debug.Log($"[GAMEPLAY][Probe] Host destroyed reportWritten={_reportWritten} started={_started}");
            }

            internal void Begin()
            {
                if (_started)
                {
                    return;
                }

                _started = true;
                Debug.Log("[GAMEPLAY][Probe] Begin invoked");
                StartCoroutine(RunGameplayProbe());
            }

            private IEnumerator RunGameplayProbe()
            {
                if (!Application.isBatchMode)
                {
                    yield break;
                }

                Debug.Log("[GAMEPLAY][Probe] Coroutine running");

                var report = new GameplayProbeReport
                {
                    generatedAt = DateTime.UtcNow.ToString("o", Invariant),
                    reason = _reason,
                };

                try
                {
                    yield return EnsureGameplaySceneLoaded(report);
                    Debug.Log($"[GAMEPLAY][Probe] Post-ensure flag={report.sceneLoaded} active={report.activeScene}");
                    if (!report.sceneLoaded)
                    {
                        yield break;
                    }

                    Debug.Log($"[GAMEPLAY][Probe] Scene ready active={report.activeScene}");

                    Debug.Log("[GAMEPLAY][Probe] CaptureCameras begin");
                    yield return CaptureCameras(report);
                    Debug.Log($"[GAMEPLAY][Probe] CaptureCameras done cameras={report.cameras.Count}");

                    Debug.Log("[GAMEPLAY][Probe] EvaluateWeaponFlow begin");
                    yield return EvaluateWeaponFlow(report);
                    Debug.Log("[GAMEPLAY][Probe] EvaluateWeaponFlow done");
                }
                finally
                {
#if UNITY_EDITOR
                    RestoreSceneContext();
#endif
                    Debug.Log("[GAMEPLAY][Probe] Finalizing gameplay probe");
                    WriteReport(report);
                    GameplayViewmodelProbe.NotifyCompleted();
                    Destroy(gameObject);
                }
            }

            private IEnumerator EnsureGameplaySceneLoaded(GameplayProbeReport report)
            {
                var targetScene = ResolveGameplaySceneName();
                report.sceneName = string.IsNullOrEmpty(targetScene) ? "<none>" : targetScene;

                if (string.IsNullOrEmpty(targetScene))
                {
                    var msg = "Gameplay probe could not resolve a gameplay scene.";
                    report.errors.Add(msg);
                    Debug.LogWarning($"[GAMEPLAY][Probe] {msg}");
                    yield break;
                }

#if UNITY_EDITOR
                if (!Application.isPlaying)
                {
                    var scenePath = GetScenePathFromBuild(targetScene);
                    if (string.IsNullOrEmpty(scenePath))
                    {
                        var msg = $"Scene '{targetScene}' missing from build list.";
                        report.errors.Add(msg);
                        Debug.LogWarning($"[GAMEPLAY][Probe] {msg}");
                        yield break;
                    }

                    try
                    {
                        _originalScene = SceneManager.GetActiveScene();
                        var opened = UnityEditor.SceneManagement.EditorSceneManager.OpenScene(scenePath, UnityEditor.SceneManagement.OpenSceneMode.Additive);
                        UnityEditor.SceneManagement.EditorSceneManager.SetActiveScene(opened);
                        _loadedScene = opened;
                        _restoreScene = true;
                        report.sceneLoaded = opened.IsValid();
                        report.activeScene = opened.name;
                        Debug.Log($"[GAMEPLAY][Probe] Opened scene '{opened.name}' via EditorSceneManager.");
                        Debug.Log($"[GAMEPLAY][Probe] sceneLoaded flag={report.sceneLoaded}");
                    }
                    catch (Exception ex)
                    {
                        var msg = $"Editor scene load failed: {ex.Message}";
                        report.errors.Add(msg);
                        Debug.LogWarning($"[GAMEPLAY][Probe] {msg}");
                        yield break;
                    }

                    var settleFrames = 10;
                    // Use frame counting because Time.realtimeSinceStartup does not advance during edit-mode batch runs.
                    while (settleFrames-- > 0)
                    {
                        yield return null;
                    }

                    var activeSceneEditor = SceneManager.GetActiveScene();
                    report.sceneLoaded = activeSceneEditor.IsValid();
                    report.activeScene = activeSceneEditor.name;
                    yield break;
                }
#endif

                if (!string.Equals(SceneManager.GetActiveScene().name, targetScene, StringComparison.OrdinalIgnoreCase))
                {
                    var loadOp = SceneManager.LoadSceneAsync(targetScene, LoadSceneMode.Single);
                    var timeoutAt = Time.realtimeSinceStartup + SceneLoadTimeoutSeconds;
                    while (loadOp != null && !loadOp.isDone && Time.realtimeSinceStartup < timeoutAt)
                    {
                        yield return null;
                    }

                    if (loadOp != null && !loadOp.isDone)
                    {
                        var msg = $"Timed out loading gameplay scene '{targetScene}'.";
                        report.errors.Add(msg);
                        Debug.LogWarning($"[GAMEPLAY][Probe] {msg}");
                        yield break;
                    }
                }

                var settleUntil = Time.realtimeSinceStartup + 0.5f;
                while (Time.realtimeSinceStartup < settleUntil)
                {
                    yield return null;
                }

                var activeScene = SceneManager.GetActiveScene();
                report.sceneLoaded = activeScene.IsValid();
                report.activeScene = activeScene.name;
                if (!report.sceneLoaded)
                {
                    var msg = "Active scene invalid after load.";
                    report.errors.Add(msg);
                    Debug.LogWarning($"[GAMEPLAY][Probe] {msg}");
                }
            }

            private static string ResolveGameplaySceneName()
            {
                try
                {
                    var requested = GameSession.SelectedGameplayScene;
                    if (!string.IsNullOrWhiteSpace(requested) && HasSceneInBuild(requested))
                    {
                        return requested;
                    }
                }
                catch (Exception ex)
                {
                    Debug.LogWarning($"[GAMEPLAY][Probe] GameSession lookup failed: {ex.Message}");
                }

                foreach (var candidate in PreferredGameplaySceneNames)
                {
                    if (HasSceneInBuild(candidate))
                    {
                        return candidate;
                    }
                }

                for (var i = 0; i < SceneManager.sceneCountInBuildSettings; i++)
                {
                    var path = SceneUtility.GetScenePathByBuildIndex(i);
                    var name = Path.GetFileNameWithoutExtension(path);
                    if (string.IsNullOrEmpty(name))
                    {
                        continue;
                    }

                    if (string.Equals(name, "MainMenu", StringComparison.OrdinalIgnoreCase))
                    {
                        continue;
                    }

                    if (string.Equals(name, "SampleScene", StringComparison.OrdinalIgnoreCase))
                    {
                        continue;
                    }

                    if (HasSceneInBuild(name))
                    {
                        return name;
                    }
                }

                return null;
            }

            private static bool HasSceneInBuild(string sceneName)
            {
                return !string.IsNullOrEmpty(GetScenePathFromBuild(sceneName));
            }

            private static string GetScenePathFromBuild(string sceneName)
            {
                if (string.IsNullOrEmpty(sceneName))
                {
                    return null;
                }

                for (var i = 0; i < SceneManager.sceneCountInBuildSettings; i++)
                {
                    var path = SceneUtility.GetScenePathByBuildIndex(i);
                    if (string.IsNullOrEmpty(path))
                    {
                        continue;
                    }

                    var name = Path.GetFileNameWithoutExtension(path);
                    if (string.Equals(name, sceneName, StringComparison.OrdinalIgnoreCase))
                    {
                        return path;
                    }
                }

                return null;
            }

            private IEnumerator CaptureCameras(GameplayProbeReport report)
            {
                _cameraCache.Clear();
                Debug.Log($"[GAMEPLAY][Camera] Waiting up to {CameraWaitTimeoutSeconds:F1}s for active cameras.");
                var waitStart = Time.realtimeSinceStartup;
                var deadline = Time.realtimeSinceStartup + CameraWaitTimeoutSeconds;
                while (Time.realtimeSinceStartup < deadline)
                {
                    var cameras = Camera.allCameras ?? Array.Empty<Camera>();
                    if (cameras.Length > 0)
                    {
                        _cameraCache.AddRange(cameras);
                        var elapsed = Time.realtimeSinceStartup - waitStart;
                        Debug.Log($"[GAMEPLAY][Camera] Found {cameras.Length} cameras after {elapsed:F2}s");
                        break;
                    }

                    yield return null;
                }

                if (_cameraCache.Count == 0)
                {
                    var waited = Time.realtimeSinceStartup - waitStart;
                    var msg = $"No active cameras discovered in gameplay scene after {waited:F2}s.";
                    report.warnings.Add(msg);
                    Debug.LogWarning($"[GAMEPLAY][Camera] {msg}");
                    yield break;
                }

                foreach (var camera in _cameraCache)
                {
                    if (camera == null)
                    {
                        continue;
                    }

                    var snapshot = BuildCameraSnapshot(camera);
                    report.cameras.Add(snapshot);
                    var stackLabel = snapshot.stack.Count > 0 ? string.Join("|", snapshot.stack) : "<none>";
                    var layersLabel = snapshot.cullingLayers.Count > 0 ? string.Join("|", snapshot.cullingLayers) : "<none>";
                    Debug.Log($"[GAMEPLAY][Camera] name={snapshot.name}, enabled={snapshot.enabled}, active={snapshot.active}, isMain={snapshot.isMain}, renderType={snapshot.renderType}, clearFlags={snapshot.clearFlags}, cullingMask={snapshot.cullingMaskHex}, layers={layersLabel}, nearClip={FormatFloat(snapshot.nearClip, "F4")}, stack={stackLabel}");
                }
            }

            private static CameraSnapshot BuildCameraSnapshot(Camera camera)
            {
                var snapshot = new CameraSnapshot
                {
                    name = camera.name,
                    enabled = camera.enabled,
                    active = camera.gameObject.activeInHierarchy,
                    isMain = camera == Camera.main,
                    renderType = GetCameraRenderType(camera),
                    projection = camera.orthographic ? "Orthographic" : "Perspective",
                    clearFlags = camera.clearFlags.ToString(),
                    depth = camera.depth,
                    nearClip = camera.nearClipPlane,
                    farClip = camera.farClipPlane,
                    fieldOfView = camera.orthographic ? 0f : camera.fieldOfView,
                    cullingMaskHex = $"0x{camera.cullingMask:X8}",
                };

                var maskLayers = ExtractLayersFromMask(camera.cullingMask);
                foreach (var layer in maskLayers)
                {
                    var label = LayerMask.LayerToName(layer);
                    if (string.IsNullOrEmpty(label))
                    {
                        label = $"Layer({layer})";
                    }

                    snapshot.cullingLayers.Add($"{label}({layer})");
                }

#if UNITY_RENDER_PIPELINE_URP
                var data = camera.GetUniversalAdditionalCameraData();
                if (data != null)
                {
                    snapshot.stackingRole = data.renderType.ToString();
                    if (data.renderType == CameraRenderType.Base && data.cameraStack != null)
                    {
                        foreach (var overlay in data.cameraStack)
                        {
                            if (overlay != null)
                            {
                                snapshot.stack.Add(overlay.name);
                            }
                        }
                    }
                }
#endif

                return snapshot;
            }

            private IEnumerator EvaluateWeaponFlow(GameplayProbeReport report)
            {
                Debug.Log("[GAMEPLAY][Equip] EvaluateWeaponFlow started");
                var equip = new GameplayEquipSnapshot();
                report.equip = equip;

                var player = FindPlayerControllerInstance();
                equip.playerFound = player != null;
                if (player != null)
                {
                    equip.playerName = player.name;
                    equip.playerPath = BuildRendererPath(player.transform);
                }

                WeaponManager weaponManager = null;
                Debug.Log($"[GAMEPLAY][Equip] Searching for WeaponManager up to {WeaponManagerWaitTimeoutSeconds:F1}s");
                var waitStart = Time.realtimeSinceStartup;
                var deadline = Time.realtimeSinceStartup + WeaponManagerWaitTimeoutSeconds;
                while (Time.realtimeSinceStartup < deadline)
                {
                    weaponManager = FindWeaponManagerInstance();
                    if (weaponManager != null)
                    {
                        break;
                    }

                    yield return null;
                }

                equip.weaponManagerFound = weaponManager != null;
                if (weaponManager == null)
                {
                    const string msg = "WeaponManager not found.";
                    equip.reason = msg;
                    report.errors.Add(msg);
                    Debug.LogWarning($"[GAMEPLAY][Equip] weaponManagerFound=false reason={msg}");
                    yield break;
                }

                var waited = Time.realtimeSinceStartup - waitStart;
                Debug.Log($"[GAMEPLAY][Equip] Found WeaponManager after {waited:F2}s name={weaponManager.name}");

                equip.weaponManagerName = weaponManager.name;
                equip.weaponManagerPath = BuildRendererPath(weaponManager.transform);
                equip.availableWeapons = weaponManager.availableWeapons != null ? weaponManager.availableWeapons.Count : 0;

                Debug.Log("[GAMEPLAY][Equip] Attempting equip sequence");
                yield return AttemptEquip(weaponManager, equip, report);
                Debug.Log("[GAMEPLAY][Equip] Equip sequence complete, capturing viewmodel");
                yield return CaptureViewmodel(report, weaponManager, equip);
            }

            private IEnumerator AttemptEquip(WeaponManager weaponManager, GameplayEquipSnapshot equip, GameplayProbeReport report)
            {
                equip.equipAttempted = true;

                try
                {
                    weaponManager.EnsureInitialized();
                    if (weaponManager.availableWeapons != null && weaponManager.availableWeapons.Count > 0 && SafeGetCurrentWeapon(weaponManager) == null)
                    {
                        ForceSwitchWeapon(weaponManager, 0);
                    }
                }
                catch (Exception ex)
                {
                    equip.reason = "exception";
                    equip.notes.Add(ex.Message);
                    report.errors.Add($"WeaponManager.EnsureInitialized exception: {ex.Message}");
                }

                var settleUntil = Time.realtimeSinceStartup + EquipSettleSeconds;
                while (Time.realtimeSinceStartup < settleUntil)
                {
                    yield return null;
                }

                var currentWeapon = SafeGetCurrentWeapon(weaponManager);
                equip.selectedWeapon = currentWeapon != null ? currentWeapon.weaponName : "<none>";
                equip.equipSucceeded = currentWeapon != null;
                if (!equip.equipSucceeded && string.IsNullOrEmpty(equip.reason))
                {
                    equip.reason = "currentWeapon_null";
                }
                else if (equip.equipSucceeded)
                {
                    equip.reason = "equip_success";
                }

                Debug.Log($"[GAMEPLAY][Equip] weaponManagerFound={equip.weaponManagerFound}, playerFound={equip.playerFound}, availableWeapons={equip.availableWeapons}, equipAttempted={equip.equipAttempted}, success={equip.equipSucceeded}, selectedWeapon={equip.selectedWeapon}, reason={equip.reason}");
            }

            private IEnumerator CaptureViewmodel(GameplayProbeReport report, WeaponManager weaponManager, GameplayEquipSnapshot equip)
            {
                var snapshot = new GameplayViewmodelSnapshot();
                report.viewmodel = snapshot;

                var holder = weaponManager != null ? weaponManager.weaponHolder : null;
                snapshot.holderPath = holder != null ? BuildRendererPath(holder) : "<null>";

                GameObject viewmodel = null;
                Debug.Log($"[GAMEPLAY][Viewmodel] Waiting up to {ViewmodelWaitTimeoutSeconds:F1}s for viewmodel instance");
                var waitStart = Time.realtimeSinceStartup;
                var deadline = Time.realtimeSinceStartup + ViewmodelWaitTimeoutSeconds;
                while (Time.realtimeSinceStartup < deadline)
                {
                    viewmodel = GetCurrentWeaponObject(weaponManager);
                    if (viewmodel != null)
                    {
                        break;
                    }

                    if (holder != null && holder.childCount > 0)
                    {
                        viewmodel = holder.GetChild(0).gameObject;
                        break;
                    }

                    yield return null;
                }

                if (viewmodel == null)
                {
                    snapshot.found = false;
                    snapshot.reason = "Viewmodel GameObject not found.";
                    report.errors.Add(snapshot.reason);
                    Debug.LogWarning($"[GAMEPLAY][Viewmodel] found=false reason={snapshot.reason}, holder={holder?.name ?? "<null>"}");
                    yield break;
                }

                var waited = Time.realtimeSinceStartup - waitStart;
                Debug.Log($"[GAMEPLAY][Viewmodel] Located viewmodel '{viewmodel.name}' after {waited:F2}s");

                PopulateViewmodelSnapshot(snapshot, viewmodel);
                var renderers = viewmodel.GetComponentsInChildren<Renderer>(true);
                snapshot.rendererCount = renderers.Length;
                snapshot.renderers.AddRange(BuildRendererSnapshots(renderers, _cameraCache));
                snapshot.cameraCoverage.AddRange(BuildCameraCoverage(renderers, _cameraCache));

                var coverageSummary = snapshot.cameraCoverage.Count > 0
                    ? string.Join("|", snapshot.cameraCoverage.Select(c => $"{c.camera}:{c.includesLayer}"))
                    : "<none>";

                Debug.Log($"[GAMEPLAY][Viewmodel] found=true instance={snapshot.name}, activeSelf={snapshot.activeSelf}, activeHierarchy={snapshot.activeInHierarchy}, layer={snapshot.layerName}({snapshot.layerIndex}), parentPath={snapshot.parentPath}, rendererCount={snapshot.rendererCount}, cameraCoverage={coverageSummary}");
            }

            private static void PopulateViewmodelSnapshot(GameplayViewmodelSnapshot snapshot, GameObject viewmodel)
            {
                var transform = viewmodel.transform;
                snapshot.found = true;
                snapshot.name = viewmodel.name;
                snapshot.activeSelf = viewmodel.activeSelf;
                snapshot.activeInHierarchy = viewmodel.activeInHierarchy;
                snapshot.layerIndex = viewmodel.layer;
                snapshot.layerName = ResolveLayerName(viewmodel.layer);
                snapshot.path = BuildRendererPath(transform);
                snapshot.parentPath = BuildRendererPath(transform.parent);
                snapshot.localPosition = transform.localPosition;
                snapshot.localEuler = transform.localEulerAngles;
                snapshot.localScale = transform.localScale;
                snapshot.worldPosition = transform.position;
                snapshot.worldEuler = transform.rotation.eulerAngles;
                snapshot.cameraAncestor = FindAncestorByComponent<Camera>(transform);
                snapshot.playerAncestor = FindAncestorByTag(transform, "Player");
            }

            private static string ResolveLayerName(int layerIndex)
            {
                var name = LayerMask.LayerToName(layerIndex);
                return string.IsNullOrEmpty(name) ? $"Layer({layerIndex})" : name;
            }

            private static string FindAncestorByComponent<T>(Transform transform) where T : Component
            {
                var current = transform != null ? transform.parent : null;
                while (current != null)
                {
                    if (current.GetComponent<T>() != null)
                    {
                        return current.name;
                    }

                    current = current.parent;
                }

                return "<none>";
            }

            private static string FindAncestorByTag(Transform transform, string tag)
            {
                var current = transform != null ? transform.parent : null;
                while (current != null)
                {
                    if (!string.IsNullOrEmpty(tag) && string.Equals(current.tag, tag, StringComparison.OrdinalIgnoreCase))
                    {
                        return current.name;
                    }

                    current = current.parent;
                }

                return "<none>";
            }

            private static List<RendererSnapshot> BuildRendererSnapshots(IReadOnlyList<Renderer> renderers, List<Camera> cameras)
            {
                var list = new List<RendererSnapshot>();
                if (renderers == null)
                {
                    return list;
                }

                foreach (var renderer in renderers)
                {
                    if (renderer == null)
                    {
                        continue;
                    }

                    var go = renderer.gameObject;
                    var entry = new RendererSnapshot
                    {
                        name = go.name,
                        enabled = renderer.enabled,
                        active = go.activeInHierarchy,
                        layerIndex = go.layer,
                        layerName = ResolveLayerName(go.layer),
                    };

                    var materials = renderer.sharedMaterials ?? Array.Empty<Material>();
                    foreach (var material in materials)
                    {
                        entry.materialNames.Add(material != null ? material.name : "<null>");
                        entry.shaderNames.Add(material != null && material.shader != null ? material.shader.name : "<null>");
                    }

                    if (cameras != null)
                    {
                        foreach (var camera in cameras)
                        {
                            if (camera == null)
                            {
                                continue;
                            }

                            entry.cameraCoverage.Add(new CameraCoverageSnapshot
                            {
                                camera = camera.name,
                                includesLayer = LayerIncluded(camera, go.layer),
                            });
                        }
                    }

                    list.Add(entry);
                }

                return list;
            }

            private static List<CameraCoverageSnapshot> BuildCameraCoverage(IReadOnlyList<Renderer> renderers, List<Camera> cameras)
            {
                var coverage = new List<CameraCoverageSnapshot>();
                if (renderers == null || cameras == null)
                {
                    return coverage;
                }

                foreach (var camera in cameras)
                {
                    if (camera == null)
                    {
                        continue;
                    }

                    var seesAll = true;
                    foreach (var renderer in renderers)
                    {
                        if (renderer == null)
                        {
                            continue;
                        }

                        if (!LayerIncluded(camera, renderer.gameObject.layer))
                        {
                            seesAll = false;
                            break;
                        }
                    }

                    coverage.Add(new CameraCoverageSnapshot
                    {
                        camera = camera.name,
                        includesLayer = seesAll,
                    });
                }

                return coverage;
            }

            private static WeaponManager FindWeaponManagerInstance()
            {
#if UNITY_2023_1_OR_NEWER || UNITY_6000_0_OR_NEWER
                return UnityEngine.Object.FindFirstObjectByType<WeaponManager>(FindObjectsInactive.Include);
#else
                return UnityEngine.Object.FindObjectOfType<WeaponManager>();
#endif
            }

            private static PlayerController FindPlayerControllerInstance()
            {
#if UNITY_2023_1_OR_NEWER || UNITY_6000_0_OR_NEWER
                return UnityEngine.Object.FindFirstObjectByType<PlayerController>(FindObjectsInactive.Include);
#else
                return UnityEngine.Object.FindObjectOfType<PlayerController>();
#endif
            }

            private static WeaponData SafeGetCurrentWeapon(WeaponManager weaponManager)
            {
                try
                {
                    return weaponManager != null ? weaponManager.GetCurrentWeapon() : null;
                }
                catch
                {
                    return null;
                }
            }

            private static GameObject GetCurrentWeaponObject(WeaponManager weaponManager)
            {
                if (weaponManager == null || CurrentWeaponObjectField == null)
                {
                    return null;
                }

                try
                {
                    return CurrentWeaponObjectField.GetValue(weaponManager) as GameObject;
                }
                catch
                {
                    return null;
                }
            }

            private static void ForceSwitchWeapon(WeaponManager weaponManager, int index)
            {
                if (weaponManager == null || SwitchWeaponMethod == null)
                {
                    return;
                }

                try
                {
                    SwitchWeaponMethod.Invoke(weaponManager, new object[] { index });
                }
                catch (Exception ex)
                {
                    Debug.LogWarning($"[GAMEPLAY][Equip] Reflection SwitchWeapon failed: {ex.Message}");
                }
            }

            private void WriteReport(GameplayProbeReport report)
            {
                if (_reportWritten || report == null)
                {
                    return;
                }

                _reportWritten = true;

                try
                {
                    var path = GetGameplayProbePath();
                    report.outputPath = path;
                    var directory = Path.GetDirectoryName(path);
                    if (!string.IsNullOrEmpty(directory))
                    {
                        Directory.CreateDirectory(directory);
                    }

                    var json = JsonUtility.ToJson(report, true);
                    File.WriteAllText(path, json);
                    Debug.Log($"[GAMEPLAY][Probe] gameplay_viewmodel_probe.json -> {path}");
                }
                catch (Exception ex)
                {
                    Debug.LogWarning($"[GAMEPLAY][Probe] Failed to write gameplay_viewmodel_probe.json: {ex.Message}");
                }
            }

#if UNITY_EDITOR
            private void RestoreSceneContext()
            {
                if (!_restoreScene)
                {
                    return;
                }

                try
                {
                    if (_loadedScene.IsValid())
                    {
                        UnityEditor.SceneManagement.EditorSceneManager.CloseScene(_loadedScene, true);
                    }

                    if (_originalScene.IsValid())
                    {
                        UnityEditor.SceneManagement.EditorSceneManager.SetActiveScene(_originalScene);
                    }
                }
                catch (Exception ex)
                {
                    Debug.LogWarning($"[GAMEPLAY][Probe] Scene restore failed: {ex.Message}");
                }
                finally
                {
                    _restoreScene = false;
                    _loadedScene = default;
                    _originalScene = default;
                }
            }
#endif

            private static string GetGameplayProbePath()
            {
                var projectRoot = Path.GetFullPath(Path.Combine(Application.dataPath, ".."));
                return Path.Combine(projectRoot, "Tools", "CI", "gameplay_viewmodel_probe.json");
            }
        }

        [Serializable]
        private sealed class GameplayProbeReport
        {
            public string generatedAt;
            public string reason;
            public string sceneName;
            public string activeScene;
            public bool sceneLoaded;
            public string outputPath;
            public List<string> warnings = new List<string>();
            public List<string> errors = new List<string>();
            public List<CameraSnapshot> cameras = new List<CameraSnapshot>();
            public GameplayEquipSnapshot equip;
            public GameplayViewmodelSnapshot viewmodel;
        }

        [Serializable]
        private sealed class CameraSnapshot
        {
            public string name;
            public bool enabled;
            public bool active;
            public bool isMain;
            public string renderType;
            public string projection;
            public string clearFlags;
            public float depth;
            public float nearClip;
            public float farClip;
            public float fieldOfView;
            public string cullingMaskHex;
            public string stackingRole;
            public List<string> cullingLayers = new List<string>();
            public List<string> stack = new List<string>();
        }

        [Serializable]
        private sealed class GameplayEquipSnapshot
        {
            public bool playerFound;
            public string playerName;
            public string playerPath;
            public bool weaponManagerFound;
            public string weaponManagerName;
            public string weaponManagerPath;
            public int availableWeapons;
            public bool equipAttempted;
            public bool equipSucceeded;
            public string selectedWeapon;
            public string reason;
            public List<string> notes = new List<string>();
        }

        [Serializable]
        private sealed class GameplayViewmodelSnapshot
        {
            public bool found;
            public string name;
            public bool activeSelf;
            public bool activeInHierarchy;
            public string layerName;
            public int layerIndex;
            public string path;
            public string parentPath;
            public string holderPath;
            public string cameraAncestor;
            public string playerAncestor;
            public Vector3 worldPosition;
            public Vector3 worldEuler;
            public Vector3 localPosition;
            public Vector3 localEuler;
            public Vector3 localScale;
            public int rendererCount;
            public List<RendererSnapshot> renderers = new List<RendererSnapshot>();
            public List<CameraCoverageSnapshot> cameraCoverage = new List<CameraCoverageSnapshot>();
            public string reason;
        }

        [Serializable]
        private sealed class RendererSnapshot
        {
            public string name;
            public bool enabled;
            public bool active;
            public string layerName;
            public int layerIndex;
            public List<string> materialNames = new List<string>();
            public List<string> shaderNames = new List<string>();
            public List<CameraCoverageSnapshot> cameraCoverage = new List<CameraCoverageSnapshot>();
        }

        [Serializable]
        private sealed class CameraCoverageSnapshot
        {
            public string camera;
            public bool includesLayer;
        }

        private static List<RendererDiagnostic> BuildRendererDiagnostics(IReadOnlyList<Renderer> renderers)
        {
            var diagnostics = new List<RendererDiagnostic>();
            if (renderers == null || renderers.Count == 0)
            {
                return diagnostics;
            }

            foreach (var renderer in renderers)
            {
                if (renderer == null)
                {
                    continue;
                }

                var go = renderer.gameObject;
                var layerIndex = go.layer;
                var layerName = LayerMask.LayerToName(layerIndex);
                if (string.IsNullOrEmpty(layerName))
                {
                    layerName = "Default";
                }

                var sortingLayerName = renderer.sortingLayerName;
                if (string.IsNullOrEmpty(sortingLayerName))
                {
                    sortingLayerName = "Default";
                }

                var diagnostic = new RendererDiagnostic
                {
                    Name = go.name,
                    Path = BuildRendererPath(go.transform),
                    RendererType = renderer.GetType().Name,
                    RendererEnabled = renderer.enabled,
                    GameObjectActive = go.activeInHierarchy,
                    LayerName = layerName,
                    LayerIndex = layerIndex,
                    SortingLayerName = sortingLayerName,
                    SortingLayerId = renderer.sortingLayerID,
                    SortingOrder = renderer.sortingOrder,
                    ShadowCastingMode = renderer.shadowCastingMode,
                    ReceiveShadows = renderer.receiveShadows,
                    BoundsCenter = renderer.bounds.center,
                    BoundsExtents = renderer.bounds.extents,
                };

                diagnostic.Materials.AddRange(BuildMaterialDiagnostics(renderer));
                diagnostics.Add(diagnostic);
            }

            return diagnostics;
        }

        private static IEnumerable<RendererMaterialDiagnostic> BuildMaterialDiagnostics(Renderer renderer)
        {
            var diagnostics = new List<RendererMaterialDiagnostic>();
            if (renderer == null)
            {
                return diagnostics;
            }

            var materials = renderer.sharedMaterials ?? Array.Empty<Material>();
            if (materials.Length == 0)
            {
                return diagnostics;
            }

            foreach (var material in materials)
            {
                if (material == null)
                {
                    diagnostics.Add(new RendererMaterialDiagnostic
                    {
                        Name = "<null>",
                        ShaderName = "<null>",
                        RenderQueue = 0,
                        HasColor = false,
                        ColorAlpha = null,
                        Surface = null,
                        AlphaClip = null,
                        Cutoff = null,
                        ZWrite = null,
                    });
                    continue;
                }

                var entry = new RendererMaterialDiagnostic
                {
                    Name = material.name,
                    ShaderName = material.shader != null ? material.shader.name : "<null>",
                    RenderQueue = material.renderQueue,
                    HasColor = material.HasProperty("_Color"),
                    ColorAlpha = material.HasProperty("_Color") ? (float?)material.GetColor("_Color").a : null,
                    Surface = material.HasProperty("_Surface") ? (float?)material.GetFloat("_Surface") : null,
                    AlphaClip = material.HasProperty("_AlphaClip") ? (float?)material.GetFloat("_AlphaClip") : null,
                    Cutoff = material.HasProperty("_Cutoff") ? (float?)material.GetFloat("_Cutoff") : null,
                    ZWrite = material.HasProperty("_ZWrite") ? (float?)material.GetFloat("_ZWrite") : null,
                };

                diagnostics.Add(entry);
            }

            return diagnostics;
        }

        private static string BuildRendererPath(Transform transform)
        {
            if (transform == null)
            {
                return "<none>";
            }

            var stack = new Stack<string>();
            var current = transform;
            while (current != null)
            {
                stack.Push(current.name);
                current = current.parent;
            }

            return string.Join("/", stack);
        }

        private static string FormatLayerSet(IReadOnlyCollection<int> layers)
        {
            if (layers == null || layers.Count == 0)
            {
                return "<none>";
            }

            var labels = new List<string>(layers.Count);
            foreach (var layer in layers)
            {
                if (layer < 0 || layer > 31)
                {
                    continue;
                }

                var name = LayerMask.LayerToName(layer);
                if (string.IsNullOrEmpty(name))
                {
                    name = "Default";
                }

                labels.Add($"{name}({layer})");
            }

            return labels.Count > 0 ? string.Join("|", labels) : "<none>";
        }

        private static bool AreAllLayersIncluded(Camera camera, IReadOnlyCollection<int> layers)
        {
            if (layers == null || layers.Count == 0)
            {
                return true;
            }

            if (camera == null)
            {
                return false;
            }

            foreach (var layer in layers)
            {
                if (!LayerIncluded(camera, layer))
                {
                    return false;
                }
            }

            return true;
        }

        private static IReadOnlyList<int> ExtractLayersFromMask(int mask)
        {
            var layers = new List<int>(8);
            for (var layer = 0; layer < 32; layer++)
            {
                if ((mask & (1 << layer)) != 0)
                {
                    layers.Add(layer);
                }
            }

            return layers;
        }

        private static void LogPipelineDiagnostics(Camera referenceCamera)
        {
            if (_pipelineLogged)
            {
                return;
            }

            _pipelineLogged = true;

            var pipelineAsset = GraphicsSettings.currentRenderPipeline;
            var hasPipeline = pipelineAsset != null;
            var pipelineAssetName = hasPipeline ? pipelineAsset.name : "<none>";
            var pipelineAssetType = hasPipeline ? pipelineAsset.GetType().FullName : "<none>";
            var rendererAssetName = "<none>";
            var rendererAssetType = "<none>";

#if UNITY_RENDER_PIPELINE_URP
            if (pipelineAsset is UniversalRenderPipelineAsset universalPipeline)
            {
                var scriptableRenderer = universalPipeline.GetRenderer(0);
                if (scriptableRenderer != null)
                {
                    rendererAssetName = scriptableRenderer.name;
                    rendererAssetType = scriptableRenderer.GetType().FullName;
                }
            }
#endif

            var referenceCameraName = referenceCamera != null ? referenceCamera.name : "<none>";
            var cameraRenderType = GetCameraRenderType(referenceCamera);

            Debug.Log(
                $"[WEAPON][Pipeline] hasPipeline={hasPipeline}, pipelineAsset={pipelineAssetName}, pipelineType={pipelineAssetType}, " +
                $"rendererAsset={rendererAssetName}, rendererType={rendererAssetType}, referenceCamera={referenceCameraName}, cameraRenderType={cameraRenderType}");
        }

        private static string GetCameraRenderType(Camera camera)
        {
#if UNITY_RENDER_PIPELINE_URP
            if (camera != null)
            {
                var data = camera.GetUniversalAdditionalCameraData();
                if (data != null)
                {
                    return data.renderType.ToString();
                }
            }
#endif

            return "pipeline_unknown";
        }

        private static void LogTransform(string weaponName, Transform transform, Camera referenceCamera)
        {
            if (transform == null)
            {
                return;
            }

            var worldPos = transform.position;
            var localPos = transform.localPosition;
            var localScale = transform.localScale;
            Vector3? localToReference = null;
            float? distanceToReference = null;
            if (referenceCamera != null)
            {
                localToReference = referenceCamera.transform.InverseTransformPoint(worldPos);
                distanceToReference = Vector3.Distance(referenceCamera.transform.position, worldPos);
            }

            var parentName = transform.parent != null ? transform.parent.name : "<null>";
            Debug.Log(
                $"[WEAPON][Transform] weapon={weaponName}, active={transform.gameObject.activeInHierarchy}, parent={parentName}, " +
                $"worldPos={FormatVector(worldPos)}, localPos={FormatVector(localPos)}, localScale={FormatVector(localScale)}, " +
                $"localToMain={FormatVector(localToReference)}, distFromMain={FormatFloat(distanceToReference)}");
        }

        private static List<CameraDiagnostic> LogCameraDiagnostics(
            string weaponName,
            Transform instanceTransform,
            int layerIndex,
            string layerName,
            IReadOnlyCollection<int> rendererLayers,
            Camera mainCamera,
            Camera auditCamera)
        {
            var diagnostics = new List<CameraDiagnostic>();
            var cameras = Camera.allCameras ?? Array.Empty<Camera>();
            var viewmodelCamera = IdentifyViewmodelCamera(cameras);
            if (viewmodelCamera == null && auditCamera != null)
            {
                viewmodelCamera = auditCamera;
            }

            if (cameras.Length == 0)
            {
                Debug.LogWarning("[WEAPON][Camera] No cameras were discovered during the audit run.");
                return diagnostics;
            }

            foreach (var camera in cameras)
            {
                if (camera == null)
                {
                    continue;
                }

                var active = camera.enabled && camera.gameObject.activeInHierarchy;
                var includesLayer = LayerIncluded(camera, layerIndex);
                var includesRendererLayers = AreAllLayersIncluded(camera, rendererLayers);
                var maskLayers = ExtractLayersFromMask(camera.cullingMask);
                var maskLabel = FormatLayerSet(maskLayers);
                var relative = camera.transform.InverseTransformPoint(instanceTransform.position);
                var distance = Vector3.Distance(camera.transform.position, instanceTransform.position);
                var behindCamera = relative.z < 0f;
                var isMain = mainCamera != null && camera == mainCamera;
                var isViewmodel = viewmodelCamera != null && camera == viewmodelCamera;
                var renderType = GetCameraRenderType(camera);

                diagnostics.Add(
                    new CameraDiagnostic
                    {
                        Name = camera.name,
                        Active = active,
                        IncludesLayer = includesLayer,
                        IncludesRendererLayers = includesRendererLayers,
                        BehindCamera = behindCamera,
                        IsMain = isMain,
                        IsViewmodel = isViewmodel,
                        CullingMask = camera.cullingMask,
                        CullingLayers = maskLabel,
                        NearClip = camera.nearClipPlane,
                        FieldOfView = camera.orthographic ? 0f : camera.fieldOfView,
                        RelativeZ = relative.z,
                        Distance = distance,
                        RenderType = renderType,
                    });

                var fieldOfView = camera.orthographic ? "0.00" : FormatFloat(camera.fieldOfView, "F2");
                Debug.Log(
                    $"[WEAPON][Audit] camera={camera.name}, weapon={weaponName}, active={active}, isMain={isMain}, isViewmodel={isViewmodel}, " +
                    $"nearClip={FormatFloat(camera.nearClipPlane, "F4")}, fieldOfView={fieldOfView}, orthographic={camera.orthographic}, " +
                    $"cullingIncludesViewmodel={includesLayer}, viewmodelLayer={layerName}({layerIndex}), cullingMask=0x{camera.cullingMask:X8}, " +
                    $"cullingLayers={maskLabel}, includesRendererLayers={includesRendererLayers}, renderPath={camera.actualRenderingPath}, " +
                    $"distance={FormatFloat(distance)}, relativeZ={FormatFloat(relative.z)}, behindCamera={behindCamera}, renderType={renderType}");
            }

            return diagnostics;
        }

        private static void LogHeuristics(
            string weaponName,
            bool hasInstance,
            bool viewmodelActive,
            IReadOnlyList<CameraDiagnostic> diagnostics)
        {
            var diagList = diagnostics ?? Array.Empty<CameraDiagnostic>();
            var flags = new List<string>();

            if (!hasInstance)
            {
                flags.Add("PrefabMissing");
            }

            if (!viewmodelActive)
            {
                flags.Add("ViewmodelInactive");
            }

            if (diagList.Count == 0)
            {
                flags.Add("NoActiveCameraFound");
            }
            else
            {
                if (diagList.All(diag => !diag.Active))
                {
                    flags.Add("NoActiveCameraFound");
                }

                if (diagList.All(diag => !diag.IncludesLayer))
                {
                    flags.Add("LayerExcludedByCamera");
                }

                if (diagList.All(diag => diag.BehindCamera))
                {
                    flags.Add("ViewmodelBehindCamera");
                }

                var nearClipRisk = diagList.Any(
                    diag => diag.IncludesLayer && !diag.BehindCamera && diag.RelativeZ <= diag.NearClip + 0.01f);
                if (nearClipRisk)
                {
                    flags.Add("NearClipMayHideViewmodel");
                }

                if (diagList.All(diag => !diag.IsViewmodel))
                {
                    flags.Add("ViewmodelCameraMissing");
                }
            }

            var payload = flags.Count > 0 ? string.Join("|", flags) : "<none>";
            Debug.Log($"[WEAPON][Heuristics] weapon={weaponName}, flags={payload}");
        }

        private static Camera IdentifyViewmodelCamera(IReadOnlyList<Camera> cameras)
        {
            if (cameras == null || cameras.Count == 0)
            {
                return null;
            }

            foreach (var camera in cameras)
            {
                if (camera == null)
                {
                    continue;
                }

                if (camera.name.IndexOf("viewmodel", StringComparison.OrdinalIgnoreCase) >= 0)
                {
                    return camera;
                }
            }

            foreach (var camera in cameras)
            {
                if (camera == null)
                {
                    continue;
                }

                var mask = camera.cullingMask;
                if (CountSetBits(mask) <= 2)
                {
                    return camera;
                }
            }

            return null;
        }

        private static bool LayerIncluded(Camera camera, int layerIndex)
        {
            if (camera == null)
            {
                return false;
            }

            if (layerIndex < 0 || layerIndex > 31)
            {
                return false;
            }

            var mask = camera.cullingMask;
            return (mask & (1 << layerIndex)) != 0;
        }

        private static int CountSetBits(int mask)
        {
            var bits = (uint)mask;
            var count = 0;
            while (bits != 0)
            {
                bits &= bits - 1;
                count++;
            }

            return count;
        }

        private static string FormatVector(Vector3 value)
        {
            return $"({value.x.ToString("F3", Invariant)}, {value.y.ToString("F3", Invariant)}, {value.z.ToString("F3", Invariant)})";
        }

        private static string FormatVector(Vector3? value)
        {
            return value.HasValue ? FormatVector(value.Value) : "<none>";
        }

        private static string FormatFloat(float value, string format = "F3")
        {
            return value.ToString(format, Invariant);
        }

        private static string FormatFloat(float? value, string format = "F3")
        {
            return value.HasValue ? value.Value.ToString(format, Invariant) : "<none>";
        }
    }
}
