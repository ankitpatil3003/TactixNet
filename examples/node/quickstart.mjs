/**
 * Node integration example — requires gateway on :8000 and built SDK.
 *
 *   cd sdk/typescript && npm install && npm run build
 *   cd ../../examples/node && npm install
 *   npm start
 */

import { SquadClient } from "@tactixnet/client";

const GATEWAY = process.env.TACTIXNET_GATEWAY ?? "http://127.0.0.1:8000";

async function main() {
  const squad = await SquadClient.create(GATEWAY, ["a1", "a2"], {
    objectiveRef: "quickstart",
  });
  console.log(`squad=${squad.squadId}`);
  await squad.connect();

  await squad.sendFrame({
    agent_id: "a1",
    tick: 1,
    position: [1, 2],
    heading: 0,
    visibility_polygon: [
      [0, 0],
      [1, 0],
      [1, 1],
    ],
    alert_level: "CALM",
  });

  const directive = await squad.receiveDirective();
  console.log(
    `directive tick=${directive.directive.tick} awards=${directive.directive.awards.length}`,
  );

  const events = await squad.getEvents({ count: 10 });
  console.log(`events logged=${events.total}`);

  await squad.close();
  console.log("quickstart ok");
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
