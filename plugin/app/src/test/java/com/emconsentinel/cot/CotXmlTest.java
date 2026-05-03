package com.emconsentinel.cot;

import org.junit.Test;

import static org.junit.Assert.assertFalse;
import static org.junit.Assert.assertTrue;

public class CotXmlTest {

    @Test public void formatsValidCotXmlWithEmconExtension() {
        CotEvent e = new CotEvent(
                "EMCON-Operator-test", "EMCON-1",
                1700000000000L, 30,
                48.2814, 37.1762,
                0.74, 123.5,
                "r-330zh-zhitel", 4.2, 90.0);
        String xml = CotXml.format(e);

        // Standard CoT skeleton
        assertTrue(xml.contains("<?xml version=\"1.0\""));
        assertTrue(xml.contains("<event version=\"2.0\""));
        assertTrue(xml.contains("uid=\"EMCON-Operator-test\""));
        assertTrue(xml.contains("type=\"a-f-G-U-C-I\""));
        assertTrue(xml.contains("how=\"m-g\""));

        // Operator position
        assertTrue("lat in <point>", xml.contains("lat=\"48.281400\""));
        assertTrue("lon in <point>", xml.contains("lon=\"37.176200\""));

        // Friendly metadata
        assertTrue(xml.contains("<contact callsign=\"EMCON-1\""));
        assertTrue(xml.contains("<__group name=\"Cyan\""));

        // EMCON extension
        assertTrue("emcon score", xml.contains("score=\"0.740000\""));
        assertTrue("emcon dwell", xml.contains("dwell_seconds=\"124\""));  // rounded
        assertTrue("emcon top threat", xml.contains("top_threat_id=\"r-330zh-zhitel\""));
        assertTrue("emcon top range", xml.contains("top_threat_range_km=\"4.200000\""));
        assertTrue("emcon top bearing", xml.contains("top_threat_bearing_deg=\"90.000000\""));

        assertTrue("remarks", xml.contains("<remarks>EMCON Sentinel risk update</remarks>"));
        assertTrue("event closes", xml.contains("</event>"));
    }

    @Test public void omitsTopThreatAttributesWhenNoTopThreat() {
        CotEvent e = new CotEvent("u", "c", 1700000000000L, 30,
                0, 0, 0.0, 0.0, null, 0, 0);
        String xml = CotXml.format(e);
        assertFalse("top_threat_id absent", xml.contains("top_threat_id="));
        assertFalse("top_threat_range absent", xml.contains("top_threat_range_km="));
        assertFalse("top_threat_bearing absent", xml.contains("top_threat_bearing_deg="));
        assertTrue("score still present", xml.contains("score=\"0.000000\""));
    }

    @Test public void clampsRiskScoreToUnitInterval() {
        String xmlHigh = CotXml.format(new CotEvent("u","c",0L,30,0,0, 1.5, 0, null, 0, 0));
        String xmlLow  = CotXml.format(new CotEvent("u","c",0L,30,0,0,-0.3, 0, null, 0, 0));
        assertTrue(xmlHigh.contains("score=\"1.000000\""));
        assertTrue(xmlLow.contains("score=\"0.000000\""));
    }

    @Test public void escapesXmlSpecialCharsInIdentifiers() {
        String xml = CotXml.format(new CotEvent("uid<>&\"'", "callsign<>", 0L, 30,
                0, 0, 0, 0, "id<dangerous>", 0, 0));
        assertTrue(xml.contains("uid=\"uid&lt;&gt;&amp;&quot;&apos;\""));
        assertTrue(xml.contains("callsign=\"callsign&lt;&gt;\""));
        assertTrue(xml.contains("top_threat_id=\"id&lt;dangerous&gt;\""));
    }

    @Test public void includesProperIso8601TimeStartStale() {
        // 1700000000000 ms = 2023-11-14T22:13:20.000Z
        CotEvent e = new CotEvent("u","c",1700000000000L, 30, 0,0, 0,0,null,0,0);
        String xml = CotXml.format(e);
        assertTrue(xml.contains("time=\"2023-11-14T22:13:20.000Z\""));
        assertTrue(xml.contains("start=\"2023-11-14T22:13:20.000Z\""));
        assertTrue(xml.contains("stale=\"2023-11-14T22:13:50.000Z\""));
    }
}
