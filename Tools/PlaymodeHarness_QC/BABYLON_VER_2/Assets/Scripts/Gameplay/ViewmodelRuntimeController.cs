using System.Reflection;
using Babylon.Weapons;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace Babylon.Gameplay.Viewmodel
{
    /// <summary>
    /// Ensures viewmodel profiles are applied for every loaded scene without touching authored prefabs.
    /// </summary>
    [DefaultExecutionOrder(-650)]
    internal sealed class ViewmodelRuntimeController : MonoBehaviour
    {
        private static bool _bootstrapped;

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.BeforeSceneLoad)]
        private static void Bootstrap()
        {
            if (_bootstrapped)
            {
                return;
            }

            _bootstrapped = true;
            var host = new GameObject("ViewmodelRuntimeController");
            host.hideFlags = HideFlags.HideAndDontSave;
            DontDestroyOnLoad(host);
            host.AddComponent<ViewmodelRuntimeController>();
        }

        private void OnEnable()
        {
            SceneManager.sceneLoaded += HandleSceneLoaded;
            ViewmodelConfigurator.Apply("OnEnable");
        }

        private void OnDisable()
        {
            SceneManager.sceneLoaded -= HandleSceneLoaded;
        }

        private void HandleSceneLoaded(Scene scene, LoadSceneMode mode)
        {
            ViewmodelConfigurator.Apply($"SceneLoaded:{scene.name}");
        }
    }

    internal static class ViewmodelConfigurator
    {
        private struct ViewmodelProfile
        {
            public string Weapon;
            public Vector3 FpPosition;
            public Vector3 FpEuler;
            public Vector3 FpScale;
            public ViewmodelTemplate Template;

            public ViewmodelProfile(string weapon, Vector3 position, Vector3 euler, Vector3 scale, ViewmodelTemplate template)
            {
                Weapon = weapon;
                FpPosition = position;
                FpEuler = euler;
                FpScale = scale;
                Template = template;
            }
        }

        private static readonly ViewmodelProfile[] Profiles =
        {
            new ViewmodelProfile("Pistol", new Vector3(0.3f, -0.3f, 0.5f), new Vector3(-10f, -5f, 0f), Vector3.one, ViewmodelTemplate.Pistol),
            new ViewmodelProfile("Combat Pistol", new Vector3(0.3f, -0.3f, 0.5f), new Vector3(-10f, -5f, 0f), Vector3.one, ViewmodelTemplate.Pistol),
            new ViewmodelProfile("Assault Rifle", new Vector3(0.25f, -0.25f, 0.4f), new Vector3(-5f, -3f, 0f), Vector3.one, ViewmodelTemplate.Rifle),
            new ViewmodelProfile("AssaultRifle", new Vector3(0.25f, -0.25f, 0.4f), new Vector3(-5f, -3f, 0f), Vector3.one, ViewmodelTemplate.Rifle),
            new ViewmodelProfile("Shotgun", new Vector3(0.28f, -0.28f, 0.45f), new Vector3(-6f, -4f, 0f), Vector3.one, ViewmodelTemplate.Shotgun),
            new ViewmodelProfile("SMG", new Vector3(0.27f, -0.27f, 0.42f), new Vector3(-6f, -4f, 0f), Vector3.one, ViewmodelTemplate.Rifle),
            new ViewmodelProfile("LMG", new Vector3(0.32f, -0.3f, 0.38f), new Vector3(-4f, -2f, 0f), Vector3.one, ViewmodelTemplate.Rifle),
            new ViewmodelProfile("Sniper Rifle", new Vector3(0.28f, -0.27f, 0.46f), new Vector3(-4f, -2f, 0f), Vector3.one, ViewmodelTemplate.Rifle),
            new ViewmodelProfile("Laser Rifle", new Vector3(0.25f, -0.26f, 0.43f), new Vector3(-5f, -3f, 0f), Vector3.one, ViewmodelTemplate.Rifle),
            new ViewmodelProfile("RocketLauncher", new Vector3(0.35f, -0.25f, 0.5f), new Vector3(-4f, -2f, 5f), Vector3.one, ViewmodelTemplate.Shotgun),
        };

        private static readonly MethodInfo RebuildMethod = typeof(WeaponManager).GetMethod("RebuildCurrentWeaponView", BindingFlags.Instance | BindingFlags.NonPublic);

        internal static void Apply(string reason)
        {
            var managers = Resources.FindObjectsOfTypeAll<WeaponManager>();
            foreach (var manager in managers)
            {
                Apply(manager, reason);
            }
        }

        private static void Apply(WeaponManager manager, string reason)
        {
            if (manager == null || manager.availableWeapons == null || manager.availableWeapons.Count == 0)
            {
                return;
            }

            var mutated = false;
            foreach (var weapon in manager.availableWeapons)
            {
                mutated |= ApplyProfile(weapon);
            }

            if (!mutated)
            {
                return;
            }

            manager.EnsureInitialized();
            TryRebuildView(manager);
            Debug.Log($"[ViewmodelConfigurator] Reapplied viewmodel profiles for '{manager.name}' ({reason}).");
        }

        private static bool ApplyProfile(WeaponData weapon)
        {
            if (weapon == null)
            {
                return false;
            }

            bool changed = false;
            if (TryGetProfile(weapon.weaponName, out var profile))
            {
                changed |= AssignVector(ref weapon.fpLocalPosition, profile.FpPosition);
                changed |= AssignVector(ref weapon.fpLocalEuler, profile.FpEuler);
                changed |= AssignVector(ref weapon.fpLocalScale, profile.FpScale);
                EnsurePrefab(weapon, profile.Template, ref changed);
            }
            else
            {
                EnsurePrefab(weapon, ViewmodelTemplate.Generic, ref changed);
                changed |= EnsureDefault(ref weapon.fpLocalPosition, new Vector3(0.2f, -0.2f, 0.45f));
                changed |= EnsureDefault(ref weapon.fpLocalEuler, new Vector3(-8f, -4f, 0f));
                changed |= EnsureDefault(ref weapon.fpLocalScale, Vector3.one);
            }

            changed |= EnsureDefault(ref weapon.tpLocalPosition, Vector3.zero);
            changed |= EnsureDefault(ref weapon.tpLocalEuler, Vector3.zero);
            changed |= EnsureDefault(ref weapon.tpLocalScale, Vector3.one);
            return changed;
        }

        private static bool TryGetProfile(string weaponName, out ViewmodelProfile profile)
        {
            if (!string.IsNullOrEmpty(weaponName))
            {
                foreach (var candidate in Profiles)
                {
                    if (string.Equals(candidate.Weapon, weaponName, System.StringComparison.OrdinalIgnoreCase))
                    {
                        profile = candidate;
                        return true;
                    }
                }
            }

            profile = default;
            return false;
        }

        internal static WeaponData CreateProfileClone(string weaponName)
        {
            var clone = ScriptableObject.CreateInstance<WeaponData>();
            clone.weaponName = weaponName ?? string.Empty;
            ConfigureForAudit(clone);
            return clone;
        }

        internal static void ConfigureForAudit(WeaponData weapon)
        {
            if (weapon == null)
            {
                return;
            }

            ApplyProfile(weapon);
        }

        private static void EnsurePrefab(WeaponData weapon, ViewmodelTemplate template, ref bool changed)
        {
            if (weapon.weaponPrefab != null)
            {
                return;
            }

            weapon.weaponPrefab = ViewmodelPrefabFactory.GetPrefab(template);
            changed = true;
        }

        private static bool AssignVector(ref Vector3 current, Vector3 expected)
        {
            if (Approximately(current, expected))
            {
                return false;
            }

            current = expected;
            return true;
        }

        private static bool EnsureDefault(ref Vector3 current, Vector3 fallback)
        {
            if (!Approximately(current, Vector3.zero))
            {
                return false;
            }

            current = fallback;
            return true;
        }

        private static bool Approximately(Vector3 lhs, Vector3 rhs)
        {
            return Vector3.SqrMagnitude(lhs - rhs) < 0.0001f;
        }

        private static void TryRebuildView(WeaponManager manager)
        {
            if (RebuildMethod == null)
            {
                return;
            }

            try
            {
                RebuildMethod.Invoke(manager, null);
            }
            catch
            {
                // Swallow reflection issues; viewmodel will rebuild on next weapon swap anyway.
            }
        }
    }
}
