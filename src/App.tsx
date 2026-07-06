import { RouterProvider } from "react-router-dom";
import { router } from "./router";

/** The whole app is the router; the shell + navigation live in the route table. */
export default function App() {
  return <RouterProvider router={router} />;
}
