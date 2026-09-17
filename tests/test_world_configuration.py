from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]


class WorldConfigurationTests(unittest.TestCase):
    def test_world_has_required_navigation_and_overview_configuration(self):
        world = (ROOT / "worlds" / "epuck_waypoint_navigation.wbt").read_text(encoding="utf-8")
        for required in (
            "DEF MAIN_VIEW Viewpoint {",
            "position 0 0 7.2",
            "fieldOfView 1.35",
            "DEF WAYPOINT_S",
            "DEF WAYPOINT_A",
            "DEF WAYPOINT_B",
            "DEF WAYPOINT_C",
            'controller "epuck_waypoint_controller"',
            "supervisor TRUE",
            "DEF TEST_BLOCKER Solid",
            "DEF ROBOT_LOCATOR Transform",
            "DEF EPUCK_ENLARGED_VISUAL Transform",
            "geometry Cylinder { height 0.035 radius 0.14 subdivision 48 }",
            'GPS { name "gps" }',
            'Compass { name "compass" }',
        ):
            self.assertIn(required, world)

    def test_waypoint_coordinates_match_reference_view(self):
        world = (ROOT / "worlds" / "epuck_waypoint_navigation.wbt").read_text(encoding="utf-8")
        self.assertIn("DEF WAYPOINT_S Solid {\n  translation -2.55 2.05", world)
        self.assertIn("DEF WAYPOINT_A Solid {\n  translation 2.25 1.95", world)
        self.assertIn("DEF WAYPOINT_B Solid {\n  translation -2.20 -2.05", world)
        self.assertIn("DEF WAYPOINT_C Solid {\n  translation 2.25 -2.05", world)

    def test_world_uses_supported_named_geometry(self):
        world = (ROOT / "worlds" / "epuck_waypoint_navigation.wbt").read_text(encoding="utf-8")
        self.assertNotIn("geometry Text", world)
        self.assertIn("Background {", world)
        self.assertIn('../protos/vendor/epuck/E-puck.proto', world)
        self.assertNotIn('EXTERNPROTO "https://', world)
        self.assertIn("DEF LABEL_HORIZONTAL Shape", world)
        self.assertIn("Navigation corridors are intentionally invisible", world)
        self.assertNotIn("ROUTE_SA_SHORT_GUIDE", world)
        self.assertNotIn("ROUTE_SA_LONG_GUIDE", world)
        self.assertNotIn("ROUTE_AC_GUIDE", world)
        self.assertNotIn("ROUTE_AB_GUIDE", world)
        self.assertNotIn("ROUTE_BC_GUIDE", world)
        for name in (
            'name "north boundary wall"',
            'name "south boundary wall"',
            'name "west boundary wall"',
            'name "east boundary wall"',
            'name "validation blocker"',
        ):
            self.assertIn(name, world)

    def test_vendored_webots_resources_are_complete(self):
        vendor = ROOT / "protos" / "vendor"
        for relative in (
            "epuck/E-puck.proto",
            "epuck/E-puckDistanceSensor.proto",
            "epuck/textures/gctronic_logo.png",
            "epuck/textures/e-puck1_plate_base_color.jpg",
            "epuck/textures/e-puck1_turret_base_color.jpg",
            "appearances/BrushedSteel.proto",
            "appearances/PorcelainChevronTiles.proto",
            "appearances/RoughConcrete.proto",
            "appearances/VarnishedPine.proto",
            "appearances/textures/porcelain_chevron/porcelain_chevron_tiles_base_color.jpg",
        ):
            self.assertTrue((vendor / relative).is_file(), relative)


if __name__ == "__main__":
    unittest.main()
